"""Runtime precondition checks for the local LLM server.

These checks run before any consult/chat/bench call reaches the model
and fail LOUD with an actionable error message if the server is not
configured correctly. They exist because two debugging sessions
(2026-04-07 and 2026-04-08) burned hours when LM Studio was loaded
with the default ``n_ctx=4096`` instead of the required ≥ 8192, and
the failure only surfaced ~80 cases into a 101-case benchmark run.

This module closes that gap: if the user forgets to set the context
length correctly, the first consult call aborts immediately with a
clear message pointing to the exact fix.

Design principles (same as the rest of the safety layer):

  - Loud by default. Silent wrong is worse than loud wrong.
  - Actionable error messages. The CHW / operator must know exactly
    what to do, not just that something is broken.
  - Zero cost on the happy path. A single HTTP GET against
    ``/api/v0/models`` is < 50 ms and runs once per process.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

from .config import LLMConfig

logger = logging.getLogger(__name__)

# Minimum context length required for the full consult pipeline
# (preflight + system prompt + 6 retrieved chunks + question +
# schema-constrained output). Below this, the pipeline silently
# truncates on complex cases and the LLM either fails to emit
# valid JSON or drops the end of the actions list. 8192 is the
# floor; 10000 is the recommended default with runway.
MIN_CTX_REQUIRED = 8192
RECOMMENDED_CTX = 10000


class RuntimePreconditionError(RuntimeError):
    """Raised when the local LLM server is not configured correctly
    for MedLocal's pipeline. Caller is expected to surface the
    message to the user verbatim — it tells them exactly what to fix.
    """


@dataclass
class LoadedModelInfo:
    """What the server reports about the currently-loaded model."""

    model_id: str
    loaded_context_length: int
    max_context_length: int
    quantization: str | None = None
    architecture: str | None = None


def query_lmstudio_loaded_model(base_url: str) -> LoadedModelInfo | None:
    """Query LM Studio's native API for the loaded model + context length.

    Returns None if the server is not LM Studio (no /api/v0 endpoint) or
    if nothing is loaded. Returns a LoadedModelInfo on success. Raises
    RuntimePreconditionError if the server is reachable but responds
    with an unexpected shape.
    """
    parsed = urlparse(base_url)
    # LM Studio's native API lives at /api/v0/models, regardless of
    # whether the chat endpoint is /v1/chat/completions
    native_url = f"{parsed.scheme}://{parsed.netloc}/api/v0/models"
    try:
        with urllib.request.urlopen(native_url, timeout=5) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            logger.debug("LM Studio native API not found at %s — skipping check", native_url)
            return None
        raise RuntimePreconditionError(
            f"LM Studio returned HTTP {exc.code} on {native_url}. "
            f"Is the server running?"
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimePreconditionError(
            f"Cannot reach LM Studio at {native_url}: {exc}. "
            f"Start LM Studio and load a model before running MedLocal."
        ) from exc
    except json.JSONDecodeError:
        logger.debug("LM Studio native API returned non-JSON — not LM Studio")
        return None

    if not isinstance(data, dict) or "data" not in data:
        return None

    for m in data["data"]:
        if m.get("state") == "loaded":
            return LoadedModelInfo(
                model_id=m.get("id", "unknown"),
                loaded_context_length=int(m.get("loaded_context_length", 0)),
                max_context_length=int(m.get("max_context_length", 0)),
                quantization=m.get("quantization"),
                architecture=m.get("arch"),
            )

    return None  # nothing loaded


def check_runtime_or_raise(cfg: LLMConfig) -> LoadedModelInfo | None:
    """Run all runtime preconditions against the configured LLM server.

    Raises :class:`RuntimePreconditionError` with an actionable message
    if the server is unreachable, no model is loaded, or the loaded
    model's context length is below :data:`MIN_CTX_REQUIRED`. Returns
    the ``LoadedModelInfo`` on success for callers that want to log it,
    or ``None`` when the server is not LM Studio (e.g. Ollama, Gemini
    API, or an OpenAI-compat server without ``/api/v0``) — in which
    case the check is skipped and the caller proceeds at its own risk.

    Typical caller pattern::

        from medlocal.runtime_check import check_runtime_or_raise, RuntimePreconditionError

        try:
            info = check_runtime_or_raise(cfg.llm)
            if info:
                logger.info("LLM server ready: %s ctx=%d", info.model_id, info.loaded_context_length)
        except RuntimePreconditionError as exc:
            print(f"⚠ {exc}", file=sys.stderr)
            sys.exit(2)
    """
    # Only check for LM Studio-style local servers. Ollama, Gemini,
    # OpenAI, etc. either enforce their own context or have a
    # different API surface.
    base_url = cfg.base_url or ""
    if "localhost" not in base_url and "127.0.0.1" not in base_url:
        logger.debug("Non-local base_url %s — skipping runtime check", base_url)
        return None

    try:
        info = query_lmstudio_loaded_model(base_url)
    except RuntimePreconditionError:
        raise

    if info is None:
        # Server reachable but either nothing loaded or not LM Studio.
        # We cannot assert anything further — let the caller proceed.
        return None

    if info.loaded_context_length < MIN_CTX_REQUIRED:
        # The exact gotcha that burned hours on 2026-04-07 and
        # 2026-04-08. Fail loud with the exact fix.
        raise RuntimePreconditionError(
            f"LM Studio loaded {info.model_id} with context length "
            f"{info.loaded_context_length}, but MedLocal requires at "
            f"least {MIN_CTX_REQUIRED} (recommended {RECOMMENDED_CTX}).\n"
            f"\n"
            f"The default auto-load in LM Studio uses 4096, which silently "
            f"truncates the preflight + consult + schema prompt on "
            f"complex cases and breaks the benchmark at case ~80 of 101.\n"
            f"\n"
            f"To fix:\n"
            f"  1. Open LM Studio\n"
            f"  2. Eject the currently loaded model\n"
            f"  3. Enable 'Manually choose model load parameters'\n"
            f"     (or hold Option/Alt while clicking the model)\n"
            f"  4. Set Context Length to {RECOMMENDED_CTX} (or at least "
            f"{MIN_CTX_REQUIRED})\n"
            f"  5. Load the model\n"
            f"  6. Re-run MedLocal\n"
            f"\n"
            f"See docs/PIPELINE.md for why this threshold is load-bearing."
        )

    logger.info(
        "Runtime check OK: %s loaded at ctx=%d (max %d), quant=%s",
        info.model_id, info.loaded_context_length,
        info.max_context_length, info.quantization,
    )
    return info
