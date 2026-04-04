"""Protocol indexer — generates searchable Q&A pairs from clinical protocols.

Uses a large teacher model (offline) to create consultation pairs that bridge
the gap between protocol language and how CHWs ask questions.

These pairs are stored in a separate vstash collection ('consultation-index')
and searched alongside the raw protocols during consultation.
"""

from __future__ import annotations

import json
import logging
import re

from .config import LLMConfig, MedLocalConfig
from .knowledge import KnowledgeBase
from .llm import chat

logger = logging.getLogger(__name__)

_INDEX_PROMPT = """\
You are creating a searchable index for a clinical decision support system.

From the protocol below, generate 3-5 question-answer pairs that a community health worker
might ask in the field. Write the QUESTIONS using simple, everyday language — the way a
health worker with basic training would describe what they see.

Rules:
1. Questions must describe SYMPTOMS, not name the disease.
   GOOD: "Child has fever, rash starting on face, and red watery eyes"
   BAD: "What is the treatment for measles?"
2. Answers must be SPECIFIC actions from the protocol (dosages, steps, referral criteria).
3. Include the most important danger signs in at least one answer.
4. Each answer must be under 80 words.
5. Write in English.

Return ONLY a JSON array:
[{"q": "symptom-based question", "a": "action-based answer from protocol"}, ...]

Protocol:
"""


def generate_index_pairs(
    protocol_text: str,
    protocol_title: str,
    llm_cfg: LLMConfig,
) -> list[dict]:
    """Generate consultation Q&A pairs from a protocol chunk."""
    try:
        response = chat(
            messages=[
                {"role": "user", "content": _INDEX_PROMPT + protocol_text},
            ],
            cfg=llm_cfg,
        )

        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]

        # Lenient JSON parsing
        try:
            items = json.loads(cleaned)
        except json.JSONDecodeError:
            bracket_start = cleaned.find("[")
            bracket_end = cleaned.rfind("]")
            if bracket_start >= 0 and bracket_end > bracket_start:
                cleaned = cleaned[bracket_start:bracket_end + 1]
                cleaned = re.sub(r",\s*]", "]", cleaned)
            items = json.loads(cleaned)

        if not isinstance(items, list):
            return []

        # Validate and tag with source
        pairs = []
        for item in items:
            if "q" in item and "a" in item:
                pairs.append({
                    "q": item["q"],
                    "a": item["a"],
                    "source": protocol_title,
                })
        return pairs

    except (json.JSONDecodeError, RuntimeError, ValueError, OSError) as exc:
        logger.warning("Index generation failed for %s: %s", protocol_title, exc)
        return []


def index_all_protocols(
    kb: KnowledgeBase,
    cfg: MedLocalConfig,
) -> int:
    """Generate consultation index pairs for all protocols in core KB.

    Stores them as markdown documents in a 'consultation-index' collection
    within the core vstash profile, so they are searched alongside protocols.
    """
    import tempfile
    import os

    teacher_cfg = cfg.get_teacher_llm()

    # Get all unique protocol titles from core
    from vstash import Memory
    from pathlib import Path
    core_mem = Memory(db=cfg.core_db, profile="medlocal-core")

    # Search broadly to get all documents
    all_results = kb.search("clinical protocol treatment management", top_k=100)
    seen_titles = set()
    total_pairs = 0

    for r in all_results:
        if r.title in seen_titles or r.profile != "core":
            continue
        seen_titles.add(r.title)

        logger.info("Indexing: %s", r.title)
        pairs = generate_index_pairs(r.text, r.title, teacher_cfg)

        if not pairs:
            continue

        # Create a searchable document from the pairs
        content = f"# Consultation Index — {r.title}\n\n"
        for i, p in enumerate(pairs, 1):
            content += f"## Scenario {i}\n"
            content += f"**Presentation:** {p['q']}\n\n"
            content += f"**Action:** {p['a']}\n\n"
            content += f"**Source protocol:** {p['source']}\n\n---\n\n"

        # Write to temp file and ingest
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", prefix=f"index-{r.title[:20]}-",
            delete=False,
        ) as f:
            f.write(content)
            tmp_path = f.name

        try:
            chunks = kb.ingest_core(tmp_path)
            total_pairs += len(pairs)
            logger.info("  -> %d pairs, %d chunks", len(pairs), chunks)
        finally:
            os.unlink(tmp_path)

    return total_pairs
