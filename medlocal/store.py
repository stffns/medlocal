"""Training store — SQLite for FSRS cards and review history."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path

from pydantic import BaseModel

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic           TEXT NOT NULL,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    level           INTEGER DEFAULT 1,
    source_title    TEXT DEFAULT '',
    source_profile  TEXT DEFAULT 'core',
    chunk_id        INTEGER DEFAULT 0,
    stability       REAL DEFAULT 0.0,
    difficulty      REAL DEFAULT 0.0,
    due             TEXT,
    last_review     TEXT,
    reps            INTEGER DEFAULT 0,
    lapses          INTEGER DEFAULT 0,
    state           INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cards_topic ON cards(topic);
CREATE INDEX IF NOT EXISTS idx_cards_due ON cards(due);

CREATE TABLE IF NOT EXISTS review_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id         INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    rating          INTEGER NOT NULL,
    elapsed_days    REAL NOT NULL,
    scheduled_days  REAL NOT NULL,
    review_at       TEXT NOT NULL
);
"""


class Rating(IntEnum):
    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


class Card(BaseModel):
    id: int | None = None
    topic: str
    question: str
    answer: str
    level: int = 1
    source_title: str = ""
    source_profile: str = "core"
    chunk_id: int = 0
    stability: float = 0.0
    difficulty: float = 0.0
    due: datetime | None = None
    last_review: datetime | None = None
    reps: int = 0
    lapses: int = 0
    state: int = 0
    created_at: datetime | None = None


class ReviewLog(BaseModel):
    card_id: int
    rating: Rating
    elapsed_days: float
    scheduled_days: float
    review_at: datetime | None = None


def _fmt(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class TrainingStore:
    """SQLite store for training cards and review history."""

    def __init__(self, db_path: str | None = None) -> None:
        # Special-case SQLite in-memory paths so the test suite can pass
        # ":memory:" without Path.resolve() turning it into a literal
        # file on disk at $CWD/:memory: (which is where that 24KB
        # phantom file in the repo root came from).
        if db_path in (":memory:", "file::memory:", "file::memory:?cache=shared"):
            self._conn = sqlite3.connect(db_path, uri=db_path.startswith("file:"))
        else:
            path = Path(db_path or "~/.medlocal/training.db").expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> TrainingStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def add_cards(self, cards: list[Card]) -> list[Card]:
        """Batch insert cards in a single transaction."""
        result = []
        now = datetime.now(timezone.utc)
        for card in cards:
            ts = _fmt(card.created_at or now)
            cur = self._conn.execute(
                """INSERT INTO cards
                   (topic, question, answer, level, source_title, source_profile,
                    chunk_id, stability, difficulty, due, last_review,
                    reps, lapses, state, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    card.topic, card.question, card.answer, card.level,
                    card.source_title, card.source_profile, card.chunk_id,
                    card.stability, card.difficulty, _fmt(card.due),
                    _fmt(card.last_review), card.reps, card.lapses,
                    card.state, ts,
                ),
            )
            result.append(
                card.model_copy(update={"id": cur.lastrowid, "created_at": _parse(ts)})
            )
        self._conn.commit()
        return result

    def get_card(self, card_id: int) -> Card | None:
        row = self._conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return self._row_to_card(row) if row else None

    def update_card(self, card: Card) -> None:
        self._conn.execute(
            """UPDATE cards SET stability=?, difficulty=?, due=?, last_review=?,
               reps=?, lapses=?, state=? WHERE id=?""",
            (
                card.stability, card.difficulty, _fmt(card.due),
                _fmt(card.last_review), card.reps, card.lapses,
                card.state, card.id,
            ),
        )
        self._conn.commit()

    def get_due_cards(self, topic: str | None = None, limit: int = 20) -> list[Card]:
        now = datetime.now(timezone.utc).isoformat()
        if topic:
            rows = self._conn.execute(
                "SELECT * FROM cards WHERE topic=? AND (due IS NULL OR due <= ?) "
                "ORDER BY due ASC LIMIT ?",
                (topic, now, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM cards WHERE due IS NULL OR due <= ? "
                "ORDER BY due ASC LIMIT ?",
                (now, limit),
            ).fetchall()
        return [self._row_to_card(r) for r in rows]

    def get_new_cards(self, topic: str | None = None, limit: int = 10) -> list[Card]:
        if topic:
            rows = self._conn.execute(
                "SELECT * FROM cards WHERE topic=? AND reps=0 "
                "ORDER BY level ASC, id ASC LIMIT ?",
                (topic, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM cards WHERE reps=0 ORDER BY level ASC, id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_card(r) for r in rows]

    def list_topics(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT topic FROM cards ORDER BY topic"
        ).fetchall()
        return [r[0] for r in rows]

    def log_review(self, log: ReviewLog) -> None:
        self._conn.execute(
            "INSERT INTO review_log (card_id, rating, elapsed_days, scheduled_days, review_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (log.card_id, log.rating, log.elapsed_days, log.scheduled_days,
             _fmt(log.review_at or datetime.now(timezone.utc))),
        )
        self._conn.commit()

    def topic_stats(self, topic: str) -> dict:
        total = self._conn.execute(
            "SELECT COUNT(*) FROM cards WHERE topic=?", (topic,)
        ).fetchone()[0]
        new = self._conn.execute(
            "SELECT COUNT(*) FROM cards WHERE topic=? AND reps=0", (topic,)
        ).fetchone()[0]
        now = datetime.now(timezone.utc).isoformat()
        due = self._conn.execute(
            "SELECT COUNT(*) FROM cards WHERE topic=? AND reps>0 AND due<=?",
            (topic, now),
        ).fetchone()[0]
        return {"topic": topic, "total": total, "new": new, "due": due}

    @staticmethod
    def _row_to_card(row: sqlite3.Row) -> Card:
        return Card(
            id=row["id"], topic=row["topic"], question=row["question"],
            answer=row["answer"], level=row["level"],
            source_title=row["source_title"],
            source_profile=row["source_profile"],
            chunk_id=row["chunk_id"],
            stability=row["stability"], difficulty=row["difficulty"],
            due=_parse(row["due"]), last_review=_parse(row["last_review"]),
            reps=row["reps"], lapses=row["lapses"], state=row["state"],
            created_at=_parse(row["created_at"]),
        )
