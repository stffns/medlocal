"""Training mode — FSRS-powered spaced repetition from clinical protocols."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from fsrs import Card as FSRSCard
from fsrs import Rating as FSRSRating
from fsrs import Scheduler

from .config import LLMConfig, MedLocalConfig
from .knowledge import KnowledgeBase
from .llm import chat
from .store import Card, Rating

logger = logging.getLogger(__name__)

_scheduler = Scheduler(
    learning_steps=(),
    relearning_steps=(),
    enable_fuzzing=False,
    desired_retention=0.9,
)

_RATING_MAP = {
    Rating.AGAIN: FSRSRating.Again,
    Rating.HARD: FSRSRating.Hard,
    Rating.GOOD: FSRSRating.Good,
    Rating.EASY: FSRSRating.Easy,
}

# ------------------------------------------------------------------ #
# Card generation                                                      #
# ------------------------------------------------------------------ #

_TEACHER_PROMPT = """\
You are a medical education expert. Generate study items from the protocol below.

Three levels:
- Level 0 (1 item): Key concept summary. "q" = topic title, "a" = 2-3 sentence summary.
- Level 1 (1-2 items): Clinical recall. "q" = question about dosage/procedure, "a" = precise answer.
- Level 2 (1-2 items): Patient scenario. "q" = realistic scenario + question, "a" = correct action + reasoning.

Rules:
- Every answer must come directly from the protocol text.
- Use the same language as the protocol.

Return ONLY a JSON array:
[{{"level": 0, "q": "...", "a": "..."}}, {{"level": 1, "q": "...", "a": "..."}}, ...]"""


def generate_cards(
    kb: KnowledgeBase,
    topic: str,
    llm_cfg: LLMConfig,
    *,
    max_chunks: int = 20,
) -> list[Card]:
    """Generate training cards from protocols related to a topic."""
    results = kb.search(topic, top_k=max_chunks)
    if not results:
        return []

    cards: list[Card] = []
    for r in results:
        module = _generate_module(r.text, r.title, llm_cfg)
        for item in module:
            cards.append(
                Card(
                    topic=topic,
                    question=item["q"],
                    answer=item["a"],
                    level=item.get("level", 1),
                    source_title=r.title,
                    source_profile=r.profile,
                    chunk_id=r.chunk_id,
                )
            )

    return cards


def _generate_module(text: str, title: str, llm_cfg: LLMConfig) -> list[dict]:
    """Generate study items from a single protocol chunk."""
    try:
        answer = chat(
            messages=[
                {"role": "system", "content": _TEACHER_PROMPT},
                {"role": "user", "content": f"Protocol: {title}\n\n{text}"},
            ],
            cfg=llm_cfg,
        )
        cleaned = answer.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]

        items = _parse_json_lenient(cleaned)
        if isinstance(items, list):
            return [
                it
                for it in items
                if "q" in it and "a" in it and it.get("level", 1) in (0, 1, 2)
            ]
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse training module: %s", exc)
    except (RuntimeError, ValueError, OSError) as exc:
        logger.warning("LLM call failed during training generation: %s", exc)

    return []


def _parse_json_lenient(text: str) -> list | None:
    """Parse JSON with recovery for common LLM formatting errors."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    bracket_pos = text.rfind("]")
    if bracket_pos > 0:
        text = text[: bracket_pos + 1]
    bracket_start = text.find("[")
    if bracket_start > 0:
        text = text[bracket_start:]

    text = re.sub(r",\s*]", "]", text)
    text = re.sub(r"}\s*{", "},{", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    objects = []
    for match in re.finditer(r"\{[^{}]+\}", text):
        try:
            obj = json.loads(match.group())
            objects.append(obj)
        except json.JSONDecodeError:
            continue

    return objects if objects else None


# ------------------------------------------------------------------ #
# Evaluation                                                           #
# ------------------------------------------------------------------ #

_JUDGE_PROMPT = """\
You are evaluating a community health worker's answer.
You have TWO sources of truth:
1. The EXPECTED ANSWER (from training materials)
2. The SOURCE PROTOCOL (the original clinical guideline)

The student's answer is correct if it matches EITHER the expected answer OR the source protocol.
If the student gives information that is in the protocol but not in the expected answer, that is still correct.
If the student gives information NOT in either source, that is wrong.

Respond with ONLY a JSON object: {{"rating": "again|hard|good|easy", "feedback": "one sentence"}}

Rating scale:
- "again": Wrong or dangerous — information contradicts the protocol.
- "hard": Partially correct but missing critical details from the protocol.
- "good": Correct with minor omissions.
- "easy": Fully correct and grounded in the protocol.

EXAMPLES:

Expected: "Give ORS 75ml/kg over 4 hours and zinc 20mg/day for 10 days"
Protocol mentions: ORS Plan B, zinc supplementation, continue breastfeeding
Student: "Give the child water and paracetamol"
{{"rating": "again", "feedback": "ORS is required, not plain water. Paracetamol is not indicated for diarrhea."}}

Expected: "Give ORS 75ml/kg over 4 hours and zinc 20mg/day for 10 days"
Protocol mentions: ORS Plan B, zinc supplementation, continue breastfeeding
Student: "Start ORS rehydration, give zinc, keep breastfeeding"
{{"rating": "easy", "feedback": "Correct treatment including continued breastfeeding from the protocol."}}

Give feedback in the same language the student used."""


def evaluate(
    question: str,
    correct_answer: str,
    student_answer: str,
    llm_cfg: LLMConfig,
    *,
    source_protocol: str | None = None,
) -> tuple[Rating, str]:
    """Evaluate a training answer against expected answer AND source protocol.

    Args:
        source_protocol: Original protocol text (from vstash chunk).
            If provided, the judge validates against both the expected answer
            and the original protocol — double grounding.

    Returns (rating, feedback).
    """
    _RATING_STR = {
        "again": Rating.AGAIN, "hard": Rating.HARD,
        "good": Rating.GOOD, "easy": Rating.EASY,
    }

    user_content = f"Question: {question}\n\nExpected answer: {correct_answer}"
    if source_protocol:
        user_content += f"\n\nSource protocol:\n{source_protocol}"
    user_content += f"\n\nStudent's answer: {student_answer}"

    try:
        response = chat(
            messages=[
                {"role": "system", "content": _JUDGE_PROMPT},
                {"role": "user", "content": user_content},
            ],
            cfg=llm_cfg,
        )

        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]

        result = json.loads(cleaned)
        rating_str = result.get("rating", "again").lower()
        feedback = result.get("feedback", "")
        return _RATING_STR.get(rating_str, Rating.AGAIN), feedback

    except (json.JSONDecodeError, RuntimeError, ValueError, OSError) as exc:
        logger.warning("Judge evaluation failed: %s", exc)
        return Rating.HARD, f"Evaluation error: {exc}"


# ------------------------------------------------------------------ #
# FSRS scheduling                                                     #
# ------------------------------------------------------------------ #


def schedule(card: Card, rating: Rating, now: datetime | None = None) -> Card:
    """Apply FSRS-6 scheduling after a review."""
    now = now or datetime.now(timezone.utc)

    fsrs_card = FSRSCard(
        due=card.due or now,
        stability=card.stability if card.stability > 0 else None,
        difficulty=card.difficulty if card.difficulty > 0 else None,
        last_review=card.last_review,
        state=2 if card.reps > 0 else 1,
        step=0,
    )

    updated, _log = _scheduler.review_card(fsrs_card, _RATING_MAP[rating], now)

    new_state = 1 if card.reps == 0 else (3 if rating == Rating.AGAIN else 2)

    return Card(
        id=card.id,
        topic=card.topic,
        question=card.question,
        answer=card.answer,
        level=card.level,
        source_title=card.source_title,
        source_profile=card.source_profile,
        chunk_id=card.chunk_id,
        stability=updated.stability or 0.0,
        difficulty=updated.difficulty or 0.0,
        due=updated.due,
        last_review=now,
        reps=card.reps + 1,
        lapses=card.lapses + (1 if rating == Rating.AGAIN else 0),
        state=new_state,
        created_at=card.created_at,
    )
