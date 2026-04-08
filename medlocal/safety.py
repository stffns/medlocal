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
    GENERATION_FAILED = 6       # Structured LLM output could not be parsed
                                # after repair — consult() returned a graceful
                                # refusal instead of a silent empty response.
    CONTROLLED_DRUG_DOSE_COMPUTED = 7  # A dose for a controlled / specialist
                                # drug (opioid, sedative, chemo, anaesthetic)
                                # slipped past PRIORITY 0.5 and reached the
                                # answer. Defense-in-depth behind the prompt.


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
    # Poisoning/ingestion — English. ANY chemical ingestion is an emergency
    # regardless of reported amount ("a little", "a sip"). The preflight
    # prompt has the rule but smaller models (E2B) do not apply it
    # consistently when a qualifier is present; this regex is the reliable
    # fast-path.
    r"(?i)\b(ingestion|ingest(ed)?|swallow(ed)?|drink|drank)\b.{0,30}\b(poison|chemical|clean(er|ing)|bleach|kerosene|gasoline|pesticide|acid|caustic|detergent)\b",
    r"(?i)\b(poison|chemical|clean(er|ing)|bleach|kerosene|gasoline|pesticide|acid|caustic|detergent)\b.{0,30}\b(ingestion|ingest(ed)?|swallow(ed)?)\b",
    r"(?i)\bpoisoning\b",
    # Poisoning/ingestion — Spanish. Pediatric chemical ingestion in the
    # CHW context is almost always phrased "[niño/niña/bebé/hijo/hija]
    # se tomó/bebió/tragó/ingirió ... [químico/limpiador/lejía/...]".
    # Same rule: any amount, any qualifier, flag as emergency.
    r"(?i)\b(se\s+)?(tom[oó]|bebi[oó]|trag[oó]|ingiri[oó])\b.{0,40}\b(qu[ií]mic\w*|limpiador\w*|limpieza|lej[ií]a|cloro|blanqueador|kerosen[oe]?|gasolina|pesticida\w*|detergente\w*|[aá]cido\w*|c[aá]ustic\w*|insecticida\w*|veneno\w*|raticida\w*|pintura|pila|batería)\b",
    r"(?i)\b(qu[ií]mic\w*|limpiador\w*|limpieza|lej[ií]a|cloro|blanqueador|kerosen[oe]?|gasolina|pesticida\w*|detergente\w*|[aá]cido\w*|c[aá]ustic\w*|insecticida\w*|veneno\w*|raticida\w*)\b.{0,40}\b(se\s+)?(tom[oó]|bebi[oó]|trag[oó]|ingiri[oó])\b",
    r"(?i)\benvenenamiento\b",
    r"(?i)\bintoxicaci[oó]n\b",
    # Mammalian bite in WHO Rabies Category III anatomy (face, head,
    # neck, hands, fingers, genitals) or any bat exposure — these are
    # ALWAYS emergencies per WHO, regardless of apparent wound severity.
    # The preflight prompt has the rule but smaller models (E2B) do not
    # apply it consistently. This regex is the reliable fast-path.
    # Covers English active ("dog bit the face"), English passive
    # ("bitten by a dog in the face"), and the Spanish equivalents.
    r"(?i)\b(dog|cat|monkey|bat|fox|jackal|livestock|mongoose|perro|gato|mono|murci[eé]lago|zorro|chacal|ganado)\s+(bite|bit|bit[eé]|scratch|araz?[oó]|mordi[oó]|atac[oó]|attack)\b.{0,80}\b(face|head|neck|hand|finger|genital|cara|rostro|cabeza|cuello|mano|dedo|genital|pene|vulva)\b",
    r"(?i)\b(face|head|neck|hand|finger|cara|rostro|cabeza|cuello|mano|dedo)\b.{0,80}\b(dog|cat|bat|perro|gato|murci[eé]lago)\s+(bite|bit|scratch|mordi[oó])\b",
    # Spanish passive voice: "mordida/mordido por perro en la cara"
    r"(?i)\bmordid[oa]s?\s+por\s+(un\s+|una\s+)?(perro|gato|mono|murci[eé]lago|zorro|chacal|ganado)\b.{0,60}\b(cara|rostro|cabeza|cuello|mano|dedo|genital|face|head|neck|hand)\b",
    r"(?i)\b(cara|rostro|cabeza|cuello|mano|dedo|face|head|neck|hand|finger)\b.{0,60}\bmordid[oa]s?\s+por\s+(un\s+|una\s+)?(perro|gato|mono|murci[eé]lago)\b",
    # English passive voice: "bitten by a dog in the face"
    r"(?i)\bbit(ten)?\s+by\s+(a\s+|an\s+)?(dog|cat|monkey|bat|fox|perro)\b.{0,60}\b(face|head|neck|hand|finger|genital|cara|cabeza|mano)\b",
    # Bat-specific — any bat encounter is Category III by WHO (even
    # scratches or in-room exposure of a sleeping child)
    r"(?i)\bbat\s+(bite|bit|scratch|in\s+the\s+room|flew\s+into|sleeping)\b",
    r"(?i)\bmurci[eé]lago\b",
    # Anaphylaxis / severe allergic reaction
    r"(?i)\banaphyla",
    r"(?i)\bangioedema\b",
    r"(?i)\b(facial|face|lip|tongue|throat)\s*(edema|swelling)\b",
    r"(?i)\b(edema|swelling)\s*(facial|face|lip|tongue|throat)\b",
    r"(?i)\bdyspnea\b",
    r"(?i)\b(bee|wasp|insect)\s*sting.{0,30}(breathing|dyspnea|anaphyla)\b",
    r"(?i)\b(breathing|dyspnea|anaphyla).{0,30}(bee|wasp|insect)\s*sting\b",
    # Self-harm / suicide
    r"(?i)\bsuicid(e|al|ality)\b",
    r"(?i)\bself[- ]?harm\b",
    r"(?i)\bkill (my|him|her)self\b",
    r"(?i)\boverdose\b",
    r"(?i)\bdeliberate\s+(ingestion|poisoning)\b",
    # Head trauma / altered consciousness
    r"(?i)\baltered mental status\b",
    r"(?i)\bhead (trauma|injury|contusion)\b",
    r"(?i)\bskull fracture\b",
    # Circulatory/bleeding
    r"(?i)\bsevere (bleeding|hemorrhage)\b",
    r"(?i)\bshock\b",
    # Obstetric
    r"(?i)\bBP\s*(≥|>=?|>)\s*160",
    r"(?i)\bblood pressure\s*(≥|>=?|>)\s*160",
    r"(?i)\beclampsia\b",
    r"(?i)\bpostpartum.{0,15}(hemorrhage|bleeding|haemorrhage)\b",
    r"(?i)\b(hemorrhage|bleeding|haemorrhage).{0,15}postpartum\b",
    r"(?i)\bheavy (bleeding|hemorrhage).{0,20}(delivery|birth|postpartum|after birth)\b",
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
# Controlled / specialist drug guard (defense in depth behind         #
# PRIORITY 0.5 of the consult system prompt). If this fires, the      #
# LLM ignored the refusal rule and computed a dose for a drug the     #
# CHW is not authorised to administer — consult() overwrites the      #
# answer with a hard refusal template and flags the response.         #
# ------------------------------------------------------------------ #

# Case-insensitive patterns for each controlled class. The patterns
# are deliberately inclusive (Spanish + English + common variants)
# because the LLM may emit the drug in either language. Additions
# go here + a unit test in tests/test_unit.py.
_CONTROLLED_PATTERNS: dict[str, str] = {
    "opioid": (
        # Covers Spanish/English spellings incl. fentanyl/fentanil/fentanilo,
        # morfina/morphine, etc.
        r"\b(?:morph?in[ae]|fentan[iy]l[oi]?|oxicodona|oxycodone|tramadol|"
        r"codein[ae]|pethidin[ae]|meperidin[ae]|metadona|methadone|"
        r"hidromorfona|hydromorphone|bupren[oó]rfina|buprenorphine)\b"
    ),
    "sedative_anaesthetic": (
        r"\b(?:midazolam|propofol|thiopent[ao]l|tiopent[ao]l|"
        r"ketamin[ae]?|etomidato?|etomidate)\b"
    ),
    "parenteral_diazepam": (
        # Diazepam IV/IM is specialist; oral diazepam is CHW-allowed.
        # We allow dose tokens between the drug name and the route marker
        # ("diazepam 10 mg IV") with a non-period gap to stay within one
        # sentence.
        r"\bdiazepam\b[^.]{0,60}?\b(?:iv|im|parenteral|intravenous|intramuscular)\b"
    ),
    "chemotherapy": (
        r"\b(?:chemother|quimioter|cisplatin[oa]?|doxorrubicin[ao]?|"
        r"doxorubicin|metotrexat[oe]|methotrexate|ciclofosfamida|"
        r"cyclophosphamide|paclitaxel|docetaxel)\b"
    ),
    "immunosuppressant": (
        r"\b(?:ciclosporin[ae]?|cyclosporin[ae]?|tacrolimus|"
        r"azatioprin[ae]|azathioprine|mofetil)\b"
    ),
    "glycopeptide": (
        # Vancomycin and teicoplanin require therapeutic drug monitoring
        # (trough levels, renal adjustment) that is specialist-level
        # regardless of EML status. A CHW should not calculate a
        # vancomycin trough in the field.
        # NOTE: aminoglycosides (gentamicin, amikacin, tobramycin) are
        # INTENTIONALLY NOT in this list — per CLAUDE.md and the
        # preflight prompt, pre-referral injectable aminoglycosides
        # ARE CHW-allowed in the LMIC context (severe pneumonia,
        # neonatal sepsis, meningitis pre-referral). Flagging them as
        # controlled caused ST06 to fail because the override replaced
        # a correct penicillin-allergy alternative with a generic
        # refusal.
        r"\b(?:vancomicin[ae]?|vancomycin|teicoplanin[ae]?)\b"
    ),
}

# Dose token — matches "5 mg", "0.5mg/kg", "2 mcg", etc. Intentionally
# broad: any time we see a number followed by a clinical unit within
# ~200 characters of a controlled drug mention, we assume the LLM is
# trying to dose it.
_CONTROLLED_DOSE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|mL|ml|IU|U)\b(?:\s*/\s*kg)?",
    re.IGNORECASE,
)


def check_controlled_drugs(answer: str) -> tuple[bool, list[str]]:
    """Detect when the answer contains a dose for a controlled/specialist drug.

    Walks the answer case-insensitively for each drug pattern. For every
    match, looks in a ±200-character window around the match for a dose
    token (``<number> mg|mcg|ml|IU|U`` optionally followed by ``/kg``).

    To avoid catching refusals that mention the drug alongside a dose
    purely pedagogically ("do NOT give morphine 0.1 mg/kg to children"),
    the check backs off when a negation cue is present within 30 chars
    before the drug mention — same pre-negation vocabulary as the
    benchmark's ``_check_absent``.

    Returns:
        ``(ok, violations)``. ``ok`` is ``False`` if at least one
        violation was found. Each violation string is
        ``"<category>:<drug_match>"`` for logging / audit.
    """
    pre_negation = [
        "not ", "no ", "never ", "avoid ", "don't ", "do not ", "nunca ",
        "no dar ", "no administr", "no se debe", "no debe", "evit",
    ]
    lower = answer.lower()
    violations: list[str] = []
    for category, pattern in _CONTROLLED_PATTERNS.items():
        for match in re.finditer(pattern, lower):
            # Pre-negation backoff — if the drug is inside a refusal
            # sentence, don't flag it. Same 60-char window the benchmark
            # uses for consistency.
            context_before = lower[max(0, match.start() - 60) : match.start()]
            if any(neg in context_before for neg in pre_negation):
                continue
            # Look for a dose token anywhere in the match itself OR
            # in a 200-char window after it. The match-internal check
            # is required for patterns like parenteral_diazepam that
            # match the whole "diazepam 10 mg IV" span — in that case
            # the dose lives inside the match, not after it.
            window_end = min(len(lower), match.end() + 200)
            search_span = match.group(0) + lower[match.end() : window_end]
            if _CONTROLLED_DOSE_RE.search(search_span):
                drug = match.group(0)
                violations.append(f"{category}:{drug}")
    return len(violations) == 0, violations


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
