"""MedLocal API — FastAPI backend for offline clinical consultation & training."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import load_config
from .consult import consult
from .knowledge import KnowledgeBase
from .store import Card, ReviewLog, TrainingStore
from .training import evaluate, generate_cards, schedule

app = FastAPI(title="MedLocal API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_cfg = None
_kb = None


def _get_cfg():
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


def _get_kb():
    global _kb
    if _kb is None:
        _kb = KnowledgeBase(_get_cfg())
    return _kb


# ------------------------------------------------------------------ #
# Request / Response models                                           #
# ------------------------------------------------------------------ #


class ConsultRequest(BaseModel):
    question: str
    history: list[dict[str, str]] = []


class ConsultResponse(BaseModel):
    answer: str
    sources: list[dict]


class IngestRequest(BaseModel):
    source: str
    profile: str = "local"  # "core" or "local"
    force: bool = False


class IngestResponse(BaseModel):
    profile: str
    chunks: int


class TrainGenerateRequest(BaseModel):
    topic: str
    max_chunks: int = 20


class TrainGenerateResponse(BaseModel):
    topic: str
    cards_created: int


class AnswerRequest(BaseModel):
    card_id: int
    answer: str


class AnswerResponse(BaseModel):
    rating: str
    feedback: str
    correct_answer: str
    next_review_days: float


class CardResponse(BaseModel):
    id: int
    topic: str
    question: str
    answer: str
    level: int
    level_label: str
    source_title: str
    reps: int
    is_read_only: bool


class SessionResponse(BaseModel):
    cards: list[CardResponse]
    due_count: int
    new_count: int


# ------------------------------------------------------------------ #
# Endpoints                                                            #
# ------------------------------------------------------------------ #

_LEVEL_LABELS = {0: "Concept", 1: "Clinical Recall", 2: "Clinical Scenario"}


def _card_response(card: Card) -> CardResponse:
    return CardResponse(
        id=card.id,
        topic=card.topic,
        question=card.question,
        answer=card.answer,
        level=card.level,
        level_label=_LEVEL_LABELS.get(card.level, "Unknown"),
        source_title=card.source_title,
        reps=card.reps,
        is_read_only=card.level == 0,
    )


@app.post("/api/consult", response_model=ConsultResponse)
def api_consult(req: ConsultRequest):
    """Clinical consultation — ask a medical question."""
    cfg = _get_cfg()
    kb = _get_kb()
    answer, sources = consult(req.question, kb, cfg.llm, history=req.history)
    return ConsultResponse(answer=answer, sources=sources)


@app.post("/api/ingest", response_model=IngestResponse)
def api_ingest(req: IngestRequest):
    """Ingest a document into core or local knowledge base."""
    kb = _get_kb()
    if req.profile == "core":
        chunks = kb.ingest_core(req.source, force=req.force)
    else:
        chunks = kb.ingest_local(req.source, force=req.force)

    if chunks == 0:
        raise HTTPException(status_code=400, detail="Ingestion failed or no content")
    return IngestResponse(profile=req.profile, chunks=chunks)


@app.post("/api/train/generate", response_model=TrainGenerateResponse)
def api_train_generate(req: TrainGenerateRequest):
    """Generate training cards for a topic."""
    cfg = _get_cfg()
    kb = _get_kb()
    cards = generate_cards(kb, req.topic, cfg.llm, max_chunks=req.max_chunks)
    if not cards:
        raise HTTPException(status_code=400, detail="No cards generated")

    with TrainingStore(cfg.recall_db) as store:
        saved = store.add_cards(cards)

    return TrainGenerateResponse(topic=req.topic, cards_created=len(saved))


@app.get("/api/train/session", response_model=SessionResponse)
def api_train_session(
    topic: str | None = Query(None),
    new_limit: int = Query(10),
):
    """Get training cards for a study session."""
    cfg = _get_cfg()
    with TrainingStore(cfg.recall_db) as store:
        due = store.get_due_cards(topic, limit=50)
        new = store.get_new_cards(topic, limit=new_limit)

    return SessionResponse(
        cards=[_card_response(c) for c in due + new],
        due_count=len(due),
        new_count=len(new),
    )


@app.post("/api/train/answer", response_model=AnswerResponse)
def api_train_answer(req: AnswerRequest):
    """Submit a training answer — evaluate and schedule."""
    cfg = _get_cfg()
    with TrainingStore(cfg.recall_db) as store:
        card = store.get_card(req.card_id)
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")

        rating, feedback = evaluate(
            card.question, card.answer, req.answer, cfg.llm,
        )

        now = datetime.now(timezone.utc)
        elapsed = 0.0
        if card.last_review:
            elapsed = (now - card.last_review).total_seconds() / 86400

        updated = schedule(card, rating, now)
        scheduled_days = (
            (updated.due - now).total_seconds() / 86400 if updated.due else 0.0
        )

        store.update_card(updated)
        store.log_review(ReviewLog(
            card_id=card.id, rating=rating,
            elapsed_days=elapsed, scheduled_days=scheduled_days, review_at=now,
        ))

    return AnswerResponse(
        rating=rating.name.lower(),
        feedback=feedback,
        correct_answer=card.answer,
        next_review_days=round(scheduled_days, 1),
    )


@app.get("/api/train/topics", response_model=list[str])
def api_train_topics():
    """List all training topics."""
    cfg = _get_cfg()
    with TrainingStore(cfg.recall_db) as store:
        return store.list_topics()


@app.get("/api/search")
def api_search(q: str = Query(...), top_k: int = Query(5)):
    """Search the knowledge base directly."""
    kb = _get_kb()
    results = kb.search(q, top_k=top_k)
    return [
        {"text": r.text[:500], "title": r.title, "score": round(r.score, 3), "profile": r.profile}
        for r in results
    ]
