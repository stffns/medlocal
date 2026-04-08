"""LLM client — unified chat interface for all providers."""

from __future__ import annotations

import logging
import os
import time

from openai import OpenAI

from .config import LLMConfig

logger = logging.getLogger(__name__)

_TIMEOUT = int(os.getenv("MEDLOCAL_LLM_TIMEOUT", "120"))
_MAX_RETRIES = 3
_RETRY_BACKOFF = (1.0, 3.0, 5.0)


def chat(
    messages: list[dict[str, str]],
    cfg: LLMConfig,
) -> str:
    """Send a chat completion and return the response text."""
    base_urls = {
        "ollama": "http://localhost:11434/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    }

    base_url = cfg.base_url or base_urls.get(cfg.provider, "https://api.openai.com/v1")
    api_key = os.getenv("MEDLOCAL_API_KEY") or cfg.api_key or "not-needed"

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=_TIMEOUT)

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=cfg.model,
                messages=messages,
                temperature=cfg.temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            err_str = str(exc).lower()
            status = str(getattr(exc, "status_code", ""))
            retryable = "rate" in err_str or "timeout" in err_str or "5" in status
            if not retryable or attempt == _MAX_RETRIES - 1:
                break
            wait = _RETRY_BACKOFF[attempt]
            logger.warning(
                "LLM call failed (attempt %d/%d), retrying in %.0fs: %s",
                attempt + 1, _MAX_RETRIES, wait, exc,
            )
            time.sleep(wait)

    raise RuntimeError(f"LLM call failed after {_MAX_RETRIES} attempts: {last_exc}") from last_exc


class StructuredLLMParseError(RuntimeError):
    """Raised when ``chat_structured`` cannot recover a valid JSON
    object from the model output. Callers (primarily ``consult()``)
    MUST catch this and return a graceful refusal rather than silently
    continuing with an empty dict — the previous silent-return behaviour
    made malformed generations indistinguishable from valid empty
    responses in audit logs and in the downstream safety layer, which
    was the real failure mode Silt flagged on 2026-04-08.
    """

    def __init__(self, raw: str, repaired: str, reason: str) -> None:
        super().__init__(f"{reason}: raw={raw[:200]!r} repaired={repaired[:200]!r}")
        self.raw = raw
        self.repaired = repaired
        self.reason = reason


def _repair_json(text: str) -> str:
    """Attempt to close unclosed structures in a truncated JSON object.

    Walks the text tracking string state (with escape handling) and a
    bracket stack. Unlike the previous naive implementation (which
    appended ``'"}'`` unconditionally and then attempted a slice-based
    repair that generated garbage on mid-array truncations), this
    version produces JSON that is at least *structurally* closeable —
    though it may still be semantically incomplete.

    Caller is expected to ``json.loads`` the result and treat failure
    as hard-stop via :class:`StructuredLLMParseError`.
    """
    text = text.rstrip()
    if not text:
        return "{}"

    in_string = False
    escape = False
    stack: list[str] = []
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack and (
                (ch == "}" and stack[-1] == "{")
                or (ch == "]" and stack[-1] == "[")
            ):
                stack.pop()
            # Unbalanced closer — leave it, json.loads will reject

    # Close an open string, then strip the trailing comma the truncation
    # often leaves dangling after the quote.
    if in_string:
        text += '"'
    text = text.rstrip().rstrip(",").rstrip()

    # Close open brackets in reverse order
    for opener in reversed(stack):
        text += "}" if opener == "{" else "]"

    return text


def chat_structured(
    messages: list[dict[str, str]],
    cfg: LLMConfig,
    schema: dict,
    schema_name: str = "response",
) -> dict:
    """Send a chat completion with JSON schema enforcement.

    Returns the parsed dict. Raises :class:`StructuredLLMParseError`
    when the model output cannot be parsed even after repair attempts —
    callers MUST catch this and degrade gracefully rather than treat it
    as "empty response".
    """
    import json

    base_urls = {
        "ollama": "http://localhost:11434/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    }

    base_url = cfg.base_url or base_urls.get(cfg.provider, "https://api.openai.com/v1")
    api_key = os.getenv("MEDLOCAL_API_KEY") or cfg.api_key or "not-needed"

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=_TIMEOUT)

    response = client.chat.completions.create(
        model=cfg.model,
        messages=messages,
        temperature=cfg.temperature,
        max_tokens=4096,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
            },
        },
    )
    text = response.choices[0].message.content or ""
    if not text.strip():
        raise StructuredLLMParseError(
            raw=text, repaired="", reason="empty model output"
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError as first_err:
        pass
    # Attempt structural repair (bracket stack + string tracking)
    repaired = _repair_json(text)
    try:
        result = json.loads(repaired)
    except json.JSONDecodeError as repair_err:
        logger.error(
            "chat_structured: repair failed. reason=%s raw_len=%d repaired_len=%d",
            repair_err, len(text), len(repaired),
        )
        raise StructuredLLMParseError(
            raw=text, repaired=repaired,
            reason=f"unrecoverable JSON: {repair_err}",
        ) from repair_err
    # Enforce that repair returned an object, not a bare value / list
    if not isinstance(result, dict):
        raise StructuredLLMParseError(
            raw=text, repaired=repaired,
            reason=f"repair returned non-object: {type(result).__name__}",
        )
    return result
