"""Training mode — FSRS-powered spaced repetition from clinical protocols."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from fsrs import Card as FSRSCard
from fsrs import Rating as FSRSRating
from fsrs import Scheduler

from .config import LLMConfig
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
You are a medical education expert creating training scenarios for community health workers.

From the clinical protocol below, generate study items at three levels:

**Level 0 — Key Concept** (1 item): Summarize the critical clinical knowledge in 2-3 sentences.
  "q" = topic title, "a" = concise summary

**Level 1 — Clinical Recall** (1-2 items): Test knowledge of protocols, dosages, \
or procedures.
  "q" = direct question about the protocol, "a" = precise answer from the guideline

**Level 2 — Clinical Scenario** (1-2 items): Present a realistic patient scenario.
  "q" = scenario description + question, "a" = correct action per protocol + reasoning

All items must be grounded in the protocol text. Do not invent medical information.
Respond in the same language as the protocol.
Return ONLY a JSON array: [{{"level": 0, "q": "...", "a": "..."}}, ...]"""


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
You are evaluating a community health worker's answer about clinical protocols.

Evaluate and respond with ONLY a JSON object:
{{"rating": "again|hard|good|easy", "feedback": "brief explanation"}}

Rating criteria:
- "again": Wrong or dangerous — could lead to patient harm.
- "hard": Partially correct but missing critical details.
- "good": Correct with minor omissions that wouldn't affect patient care.
- "easy": Perfect — demonstrates clear clinical understanding.

Focus on clinical accuracy. Accept answers in any language.
Give feedback in the same language the student used."""


def evaluate(
    question: str,
    correct_answer: str,
    student_answer: str,
    llm_cfg: LLMConfig,
) -> tuple[Rating, str]:
    """Evaluate a training answer. Returns (rating, feedback)."""
    _RATING_STR = {
        "again": Rating.AGAIN, "hard": Rating.HARD,
        "good": Rating.GOOD, "easy": Rating.EASY,
    }

    try:
        response = chat(
            messages=[
                {"role": "system", "content": _JUDGE_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\n\n"
                        f"Correct answer: {correct_answer}\n\n"
                        f"Student's answer: {student_answer}"
                    ),
                },
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
