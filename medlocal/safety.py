"""Safety layer — hallucination detection, confidence scoring, and audit logging."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path

from .config import LLMConfig, MedLocalConfig
from .knowledge import KnowledgeBase, SearchResult
from .llm import chat

logger = logging.getLogger(__name__)


class Confidence(IntEnum):
    """Confidence level for a consultation response."""
    LOW = 1       # Marginal retrieval, answer may be unreliable
    MEDIUM = 2    # Decent retrieval, answer likely correct
    HIGH = 3      # Strong retrieval match, answer well-grounded


class SafetyFlag(IntEnum):
    """Safety flags for response review."""
    OK = 0
    EMERGENCY_DETECTED = 1      # Danger signs found — must refer
    LOW_CONFIDENCE = 2          # Retrieval quality too low
    HALLUCINATION_SUSPECTED = 3 # Answer contains info not in protocols
    DOSAGE_MENTIONED = 4        # Dosage in answer — needs extra scrutiny
    URGENT_REFERRAL = 5         # LLM classified as urgent — refer within hours


# ------------------------------------------------------------------ #
# Confidence scoring                                                   #
# ------------------------------------------------------------------ #

def score_confidence(sources: list[dict], results: list[SearchResult]) -> Confidence:
    """Score confidence based on retrieval quality."""
    if not results:
        return Confidence.LOW

    best = max(r.score for r in results)
    count_relevant = sum(1 for r in results if r.score >= best * 0.7)

    # Multiple relevant chunks from same protocol = high confidence
    # Thresholds: out-of-scope ~0.008-0.010, on-scope >0.014
    if count_relevant >= 3 and best > 0.015:
        return Confidence.HIGH
    elif count_relevant >= 1 and best > 0.012:
        return Confidence.MEDIUM
    else:
        return Confidence.LOW


# ------------------------------------------------------------------ #
# Hallucination detection                                              #
# ------------------------------------------------------------------ #

_VERIFY_PROMPT = """\
You are a medical safety verifier. Compare the ANSWER against the SOURCE PROTOCOLS.

Check if the answer contains ANY information that is NOT in the source protocols.
Focus especially on: dosages, drug names, time intervals, age thresholds.

Respond with ONLY a JSON object:
{"grounded": true/false, "issues": ["list of specific claims not found in protocols"]}

If ALL claims in the answer are supported by the protocols, return {"grounded": true, "issues": []}"""


def verify_grounding(
    answer: str,
    protocol_texts: list[str],
    llm_cfg: LLMConfig,
) -> tuple[bool, list[str]]:
    """Verify that the answer is grounded in the retrieved protocols.

    Returns:
        Tuple of (is_grounded, list_of_issues).
    """
    context = "\n---\n".join(protocol_texts)

    try:
        response = chat(
            messages=[
                {"role": "system", "content": _VERIFY_PROMPT},
                {
                    "role": "user",
                    "content": f"SOURCE PROTOCOLS:\n{context}\n\nANSWER:\n{answer}",
                },
            ],
            cfg=llm_cfg,
        )

        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]

        result = json.loads(cleaned)
        return result.get("grounded", False), result.get("issues", [])

    except (json.JSONDecodeError, RuntimeError, ValueError, OSError) as exc:
        logger.warning("Safety verification failed: %s", exc)
        # If verification fails, flag as unverified rather than passing
        return False, [f"Verification unavailable: {exc}"]


# ------------------------------------------------------------------ #
# Emergency detection                                                  #
# ------------------------------------------------------------------ #

_EMERGENCY_PATTERNS = [
    # IMCI general danger signs
    r"(?i)\bunable to (drink|breastfeed|eat|feed|suck|swallow)\b",
    r"(?i)\bcannot (drink|breastfeed|eat|feed|suck|swallow)\b",
    r"(?i)\bdysphagia\b",
    r"(?i)\bvomit(s|ing) everything\b",
    r"(?i)\bintractable (vomiting|emesis)\b",
    r"(?i)\bpersistent (vomiting|emesis)\b",
    r"(?i)\bconvulsion",
    r"(?i)\bletharg(ic|y)\b",
    r"(?i)\bunconscious",
    r"(?i)\bnot breathing\b",
    # Respiratory emergency (IMCI: chest indrawing = severe pneumonia in infants)
    r"(?i)\bchest (in)?drawing\b",
    r"(?i)\b(costal|intercostal|subcostal)\s*(retraction|recession)s?\b",
    r"(?i)\bsevere.{0,10}(respiratory|breathing) distress\b",
    r"(?i)\bstridor\b",
    # Circulatory/bleeding
    r"(?i)\bsevere (bleeding|hemorrhage)\b",
    r"(?i)\bshock\b",
    # Obstetric
    r"(?i)\bBP\s*(≥|>=?|>)\s*160",
    r"(?i)\bblood pressure\s*(≥|>=?|>)\s*160",
    r"(?i)\beclampsia\b",
    # Nutrition
    r"(?i)\bsevere dehydration\b",
    r"(?i)\bsevere (acute )?malnutrition\b",
    r"(?i)\bMUAC\s*(<|<=?|<)\s*11\.5",
    r"(?i)\bbilateral.{0,20}edema\b",
]

_EMERGENCY_COMPILED = [re.compile(p) for p in _EMERGENCY_PATTERNS]


def detect_emergency(question: str) -> tuple[bool, list[str]]:
    """Detect emergency keywords in the question.

    Returns:
        Tuple of (is_emergency, list_of_matched_patterns).
    """
    matches = []
    for pattern in _EMERGENCY_COMPILED:
        if pattern.search(question):
            matches.append(pattern.pattern)
    return bool(matches), matches


# ------------------------------------------------------------------ #
# Dosage cross-check                                                   #
# ------------------------------------------------------------------ #

_DOSAGE_PATTERN = re.compile(
    r"\b\d+\.?\d*\s*(?:mg|ml|mL|g|mcg|IU|units?|tablets?|doses?)"
    r"(?:\s*/\s*(?:kg|day|hour|dose))?"
)


def extract_dosages(text: str) -> list[str]:
    """Extract dosage mentions from text."""
    return _DOSAGE_PATTERN.findall(text)


def check_dosages(answer: str, protocol_texts: list[str]) -> tuple[bool, list[str]]:
    """Check if dosages in the answer appear in the source protocols.

    Returns:
        Tuple of (all_found, list_of_unmatched_dosages).
    """
    answer_dosages = extract_dosages(answer)
    if not answer_dosages:
        return True, []

    protocol_text = " ".join(protocol_texts)
    protocol_dosages = set(extract_dosages(protocol_text))

    # Normalize for comparison
    def normalize(d: str) -> str:
        return re.sub(r"\s+", "", d.lower())

    protocol_normalized = {normalize(d) for d in protocol_dosages}
    unmatched = [
        d for d in answer_dosages
        if normalize(d) not in protocol_normalized
    ]

    return len(unmatched) == 0, unmatched


# ------------------------------------------------------------------ #
# Audit log                                                            #
# ------------------------------------------------------------------ #

_AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    mode            TEXT NOT NULL,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    sources_json    TEXT NOT NULL,
    confidence      INTEGER NOT NULL,
    safety_flags    TEXT NOT NULL,
    grounded        INTEGER,
    issues_json     TEXT,
    emergency       INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp);
"""


class AuditLog:
    """SQLite audit log for all consultation responses."""

    def __init__(self, cfg: MedLocalConfig) -> None:
        path = Path(cfg.core_db).parent / "audit.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.executescript(_AUDIT_SCHEMA)

    def log(
        self,
        *,
        mode: str,
        question: str,
        answer: str,
        sources: list[dict],
        confidence: Confidence,
        safety_flags: list[SafetyFlag],
        grounded: bool | None = None,
        issues: list[str] | None = None,
        emergency: bool = False,
    ) -> int:
        """Log a consultation interaction. Returns the log ID."""
        cur = self._conn.execute(
            """INSERT INTO audit_log
               (timestamp, mode, question, answer, sources_json, confidence,
                safety_flags, grounded, issues_json, emergency)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                mode,
                question,
                answer,
                json.dumps(sources),
                confidence,
                json.dumps([f.name for f in safety_flags]),
                1 if grounded else (0 if grounded is not None else None),
                json.dumps(issues) if issues else None,
                1 if emergency else 0,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def close(self) -> None:
        self._conn.close()
