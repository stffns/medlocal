"""Vision mode — image analysis via Gemma 4 multimodal (OpenAI-compatible API)."""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from openai import OpenAI

from .config import LLMConfig, MedLocalConfig
from .knowledge import KnowledgeBase

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Vision prompts                                                       #
# ------------------------------------------------------------------ #

_TRIAGE_PROMPT_BASE = """\
You are a clinical visual assessment assistant for community health workers.

Describe what you see in this clinical photo using medical terminology.
Focus on: location, size, color, texture, borders, surrounding tissue.
Do NOT diagnose. Only describe the visual findings.

Keep your description under 100 words. Use simple clinical language.
{language_instruction}
End with: "Suggested search terms: [3-5 medical terms for protocol lookup]"
"""

_MEDICATION_PROMPT = """\
You are a medication identification assistant for community health workers.

From this photo of a medication or its packaging, extract:
1. Drug name (generic and brand if visible)
2. Dosage/strength
3. Form (tablet, capsule, syrup, injection, etc.)
4. Manufacturer (if visible)
5. Expiry date (if visible)

If you cannot identify the medication clearly, say so.
Do NOT guess if the text is not readable.
"""

_SCAN_PROMPT = """\
Extract ALL text from this photo of a medical document.
Preserve the structure: headings, lists, tables, numbered steps.
If parts are unclear, mark them as [illegible].
Output the extracted text as clean markdown.
"""


# ------------------------------------------------------------------ #
# Image encoding                                                       #
# ------------------------------------------------------------------ #

def _encode_image(image_path: str) -> tuple[str, str]:
    """Encode an image file to base64 data URI."""
    path = Path(image_path)
    suffix = path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".bmp": "image/bmp",
    }
    media_type = media_types.get(suffix, "image/jpeg")
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    return b64, media_type


def _chat_with_image(
    prompt: str,
    image_b64: str,
    media_type: str,
    cfg: LLMConfig,
) -> str:
    """Send a chat completion with an image to an OpenAI-compatible API."""
    base_url = cfg.base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"
    api_key = os.getenv("MEDLOCAL_API_KEY") or cfg.api_key or "not-needed"

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=120)

    response = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_b64}",
                        },
                    },
                ],
            }
        ],
        temperature=cfg.temperature,
        max_tokens=1024,
    )
    return response.choices[0].message.content or ""


# ------------------------------------------------------------------ #
# Vision workflows                                                     #
# ------------------------------------------------------------------ #

def triage(image_path: str, cfg: LLMConfig, *, user_context: str = "") -> str:
    """Describe clinical findings in an image.

    Returns a text description with suggested search terms.
    """
    if user_context.strip():
        lang_instruction = (
            f'The health worker reports: "{user_context}"\n'
            f'Use this context to focus your description. '
            f'Respond in the SAME LANGUAGE as the health worker.'
        )
    else:
        lang_instruction = ""
    prompt = _TRIAGE_PROMPT_BASE.format(language_instruction=lang_instruction)

    b64, media = _encode_image(image_path)
    return _chat_with_image(prompt, b64, media, cfg)


def identify_medication(image_path: str, cfg: LLMConfig) -> str:
    """Identify a medication from a photo of the drug or packaging."""
    b64, media = _encode_image(image_path)
    return _chat_with_image(_MEDICATION_PROMPT, b64, media, cfg)


def scan_document(image_path: str, cfg: LLMConfig) -> str:
    """Extract text from a photo of a medical document."""
    b64, media = _encode_image(image_path)
    return _chat_with_image(_SCAN_PROMPT, b64, media, cfg)


def triage_and_consult(
    image_path: str,
    kb: KnowledgeBase,
    cfg: MedLocalConfig,
    *,
    user_context: str = "",
) -> dict:
    """Full pipeline: image → visual description → protocol retrieval → clinical guidance.

    Args:
        user_context: Additional symptoms/context provided by the health worker.

    Returns dict with: description, answer, sources, confidence, emergency.
    """
    import re
    from .consult import consult

    # Step 1: Describe what we see (in the user's language)
    description = triage(image_path, cfg.llm, user_context=user_context)

    # Step 2: Extract search terms from description (model appends them)
    search_terms = ""
    match = re.search(r"Suggested search terms?:\s*(.+)", description, re.IGNORECASE)
    if match:
        search_terms = match.group(1).strip()

    # Step 3: Search using user context (clinical symptoms), NOT visual terms
    # Visual terms like "papules, macules" pull in wrong protocols (dermatitis instead of measles)
    # The visual description goes to the LLM as context, not to retrieval
    if user_context.strip():
        query = user_context
    else:
        query = search_terms or description[:100]

    # Step 4: Consult with visual description injected as additional context
    visual_ctx = description.replace(search_terms, "").strip() if search_terms else description
    enriched_query = f"{query}\n\n[Visual examination: {visual_ctx}]"
    result = consult(enriched_query, kb, cfg.llm)
    result["description"] = description

    return result


def scan_and_ingest(
    image_path: str,
    kb: KnowledgeBase,
    cfg: MedLocalConfig,
) -> dict:
    """Scan a document photo and ingest the text into local profile.

    Returns dict with: text, chunks.
    """
    import tempfile

    text = scan_document(image_path, cfg.llm)

    if not text or len(text.strip()) < 50:
        return {"text": text, "chunks": 0}

    # Write extracted text to temp file and ingest
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(text)
        tmp_path = f.name

    try:
        chunks = kb.ingest_local(tmp_path)
    finally:
        os.unlink(tmp_path)

    return {"text": text, "chunks": chunks}
