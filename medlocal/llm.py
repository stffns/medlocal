"""LLM client — unified chat interface for all providers."""

from __future__ import annotations

import logging
import os
import time

from openai import OpenAI

from .config import LLMConfig

logger = logging.getLogger(__name__)

_TIMEOUT = int(os.getenv("MEDLOCAL_LLM_TIMEOUT", "120"))
_MAX_RETRIES = 5
_RETRY_BACKOFF = (2.0, 10.0, 30.0, 60.0, 90.0)


def _parse_retry_delay(err_str: str) -> float | None:
    """Extract Gemini 'retryDelay: 59s' or 'retry in 59.78s' from error."""
    import re as _re
    m = _re.search(r"retry(?:Delay|\s+in)[^\d]*(\d+(?:\.\d+)?)", err_str)
    if m:
        return float(m.group(1))
    return None


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

    # Gemma quirks: merge system into user for gemma-3/3n (no system role).
    model_lower = cfg.model.lower()
    if ("gemma-3" in model_lower or "gemma-4" in model_lower) and messages and messages[0].get("role") == "system":
        messages = [dict(m) for m in messages]
        no_think = (
            "Respond directly. Do NOT emit <thought> or reasoning blocks. "
            "Give the final answer only.\n\n"
        )
        system_content = no_think + messages[0]["content"]
        if "gemma-3" in model_lower:
            # Merge system into first user message
            for i, m in enumerate(messages[1:], start=1):
                if m.get("role") == "user":
                    messages[i] = dict(m)
                    messages[i]["content"] = system_content + "\n\n" + m["content"]
                    messages = messages[1:]
                    break
        else:
            messages[0]["content"] = system_content

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=cfg.model,
                messages=messages,
                temperature=cfg.temperature,
            )
            text = response.choices[0].message.content or ""
            # Strip Gemma 4 thinking blocks (Gemini API)
            import re as _re_t
            return _re_t.sub(r"<thought>.*?</thought>\s*", "", text, flags=_re_t.DOTALL)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            err_str = str(exc).lower()
            status = str(getattr(exc, "status_code", ""))
            retryable = "rate" in err_str or "timeout" in err_str or "5" in status or "429" in err_str or "resource_exhausted" in err_str
            if not retryable or attempt == _MAX_RETRIES - 1:
                break
            # Honor server-suggested retry delay, otherwise use backoff
            server_delay = _parse_retry_delay(str(exc))
            wait = max(server_delay + 2, _RETRY_BACKOFF[attempt]) if server_delay else _RETRY_BACKOFF[attempt]
            logger.warning(
                "LLM call failed (attempt %d/%d), retrying in %.0fs: %s",
                attempt + 1, _MAX_RETRIES, wait, str(exc)[:200],
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

    # Gemma models via Gemini API quirks:
    # - gemma-4-*: response_format=json_schema hangs (6+ min). Use prompt-based schema.
    # - gemma-3n-*: does not support system role. Concatenate system into user.
    # Both strip <thought> reasoning blocks post-hoc.
    model_lower = cfg.model.lower()
    is_gemma_quirky = (
        "gemma-4" in model_lower
        or "gemma-3n" in model_lower
        or "gemma-3-" in model_lower
    )
    use_schema_enforcement = not is_gemma_quirky

    if is_gemma_quirky and messages and messages[0].get("role") == "system":
        messages = [dict(m) for m in messages]  # shallow copy
        import json as _json
        schema_hint = (
            "CRITICAL: Respond directly with a single valid JSON object only. "
            "Do NOT emit <thought> or reasoning blocks. Do NOT explain your "
            "reasoning. Do NOT wrap in markdown fences. The response MUST "
            f"conform to this JSON schema:\n{_json.dumps(schema, indent=2)}\n\n"
        )
        system_content = schema_hint + messages[0]["content"]

        # gemma-3n and gemma-3 don't support system role — merge into user
        if "gemma-3" in model_lower:
            # Find first user message and prepend system content
            for i, m in enumerate(messages[1:], start=1):
                if m.get("role") == "user":
                    messages[i] = dict(m)
                    messages[i]["content"] = system_content + "\n\n" + m["content"]
                    messages = messages[1:]  # drop the system message
                    break
        else:
            messages[0]["content"] = system_content

    create_kwargs = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "max_tokens": 4096,
    }
    if use_schema_enforcement:
        create_kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema},
        }
    # Retry loop for rate limits (Gemini API 15k tokens/min free tier)
    response = None
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.chat.completions.create(**create_kwargs)
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            err_str = str(exc).lower()
            status = str(getattr(exc, "status_code", ""))
            retryable = "rate" in err_str or "timeout" in err_str or "5" in status or "429" in err_str or "resource_exhausted" in err_str
            if not retryable or attempt == _MAX_RETRIES - 1:
                raise
            server_delay = _parse_retry_delay(str(exc))
            wait = max(server_delay + 2, _RETRY_BACKOFF[attempt]) if server_delay else _RETRY_BACKOFF[attempt]
            logger.warning(
                "chat_structured failed (attempt %d/%d), retrying in %.0fs",
                attempt + 1, _MAX_RETRIES, wait,
            )
            time.sleep(wait)
    if response is None:
        raise RuntimeError(f"chat_structured failed after {_MAX_RETRIES} attempts: {last_exc}") from last_exc
    text = response.choices[0].message.content or ""
    # Strip <thought>...</thought> blocks (Gemma 4 thinking mode) and
    # markdown code fences (Gemma 3/3n habit) before parsing JSON.
    import re as _re_thought
    text = _re_thought.sub(r"<thought>.*?</thought>\s*", "", text, flags=_re_thought.DOTALL)
    text = text.strip()
    # Remove markdown fences: ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        # Strip opening fence (with optional language tag)
        text = _re_thought.sub(r"^```(?:json)?\s*\n?", "", text)
        # Strip closing fence
        text = _re_thought.sub(r"\n?```\s*$", "", text)
        text = text.strip()
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
