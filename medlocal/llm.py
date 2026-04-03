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
    api_key = cfg.api_key or os.getenv("MEDLOCAL_API_KEY", "not-needed")

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
