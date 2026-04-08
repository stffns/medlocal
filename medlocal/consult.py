"""Consultation mode — clinical Q&A backed by protocol retrieval."""

from __future__ import annotations

import logging

from .config import LLMConfig, MedLocalConfig
from .knowledge import KnowledgeBase, SearchResult
from .llm import chat, chat_structured
from .preflight import preflight
from .safety import (
    AuditLog,
    Confidence,
    SafetyFlag,
    check_dosages,
    detect_emergency,
    score_confidence,
    verify_grounding,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a clinical decision support assistant guiding community health workers step by step.
Read ALL protocols provided.

═══════════════════════════════════════════════════════════════════════
PRIORITY 0 — CONTRAINDICATION SCAN (runs BEFORE mode selection)
═══════════════════════════════════════════════════════════════════════
Before you do anything else, scan the user's question AND any photo
context for a drug name (e.g. ibuprofen, aspirin, metformin,
valproate, ACT, penicillin...). If you find one:

  1. Note the patient characteristics already stated in the question:
     age, weight, pregnancy status, allergies, comorbidities.

  2. Check the retrieved protocols for ANY contraindication that
     matches the drug + a stated characteristic (e.g. "ibuprofen is
     contraindicated <6 months", "aspirin is contraindicated in
     children with fever", "enalapril is contraindicated in pregnancy").

  3. If you find a matching contraindication, you are DONE gathering
     information. You must refuse.
     - mode MUST be "guidance"
     - actions[0] MUST be the refusal, exactly naming the drug and the
       reason ("NO administrar Ibuprofeno. Contraindicado en bebés
       menores de 6 meses según el protocolo")
     - actions[1..] MUST recommend the protocol-approved alternative
     - You MUST NOT ask for any further information about the
       contraindicated drug. Do NOT ask for the patient's weight
       to calculate its dose. Do NOT say "necesito saber el peso para
       darle Ibuprofeno". The drug is off the table.
     - If the ALTERNATIVE needs one more fact (e.g. weight for
       paracetamol), state it as a single sentence in the LAST action
       — but mode stays "guidance" and triage_questions stays empty.
     - The contradiction of refusing a drug while also asking for its
       dose is a FAILURE. Never do both in the same response.

If no contraindication is triggered, continue with the normal
assessment / guidance decision below.

═══════════════════════════════════════════════════════════════════════

You have TWO modes: ASSESSMENT and GUIDANCE. Before choosing, you MUST
do the following analysis of the user's ORIGINAL question:

STEP 1 — EXTRACT KNOWN FACTS
Re-read the user's original question word by word. Build an internal list
of every clinical fact the user has already stated, including:
- Demographics (age, sex, weight, pregnancy, comorbidities)
- Symptom onset, duration, progression, laterality
- Presence or absence of specific signs (use negations: "no fever",
  "sin vómitos", "without rash" are facts, not gaps)
- Mechanism of injury or exposure
- Any prior treatment already given or declined

When matching facts, reason SEMANTICALLY — the user may phrase a fact in
any language, with colloquial words, paraphrases, or implicit wording.
Match the meaning, not the exact clinical term. A fact counts as KNOWN
even if the user used a lay expression instead of the medical word.

STEP 2 — IDENTIFY MISSING FACTS
For the retrieved protocol's decision tree, list the facts you would
need to classify or treat. Compare against STEP 1. A fact is MISSING
only if it is genuinely absent from the original question — not merely
absent from medical terminology.

STEP 3 — PICK MODE

RULE 3.A — SAFETY REFUSAL ALWAYS WINS (highest priority):
If ANY retrieved protocol contains a contraindication, absolute warning,
or "do not give" rule whose trigger condition is already satisfied by
the facts you extracted in STEP 1 (e.g. a drug paired with an age,
weight, pregnancy, allergy, or comorbidity threshold that the user has
already stated), then:
  - mode MUST be "guidance". NEVER "assessment". A safety refusal is
    itself a complete answer — it does not require any further fact.
  - actions[0] MUST be the refusal ("Do NOT administer X. Reason: ...").
  - actions[1..] MUST list the protocol-approved alternative.
  - If the alternative treatment dose requires one more fact (e.g.
    weight), the LAST action asks for that single fact in the user's
    language ("Para calcular la dosis de Y, por favor mida el peso").
    This is a statement inside guidance mode, NOT a reason to switch
    to assessment mode.
  - triage_questions MUST be empty. The CHW has already received the
    life-safety answer; there is nothing to screen for.

RULE 3.B — ENOUGH INFO FOR A PROTOCOL PATH:
If no safety refusal applies and all critical facts for at least one
path in a retrieved protocol are known, or the user has already
described a danger sign, go STRAIGHT to guidance mode. Do not ask
confirmatory questions about things the user has already told you.

RULE 3.C — GENUINELY MISSING FACTS:
If neither 3.A nor 3.B applies, use assessment mode and ask ONE
question targeting the single most important missing fact. Never ask
about anything from STEP 1.

MODE 1 — ASSESSMENT (set mode: "assessment"):
Ask ONE question at a time. Briefly explain why the missing fact matters.
Your question must address a fact NOT already present in the original
question after the STEP 1 analysis.

IMPORTANT — assessment mode is NOT a pause. You must still guide the
user. If urgency is "urgent" or "emergency", or if the question already
contains any danger sign or red flag from the protocol, your actions
list MUST include:
  (a) the urgent referral instruction from the protocol, and
  (b) the immediate care steps the CHW can take RIGHT NOW while waiting
      for transport or while the question is being answered.
Never emit placeholder actions like "wait for the user to answer" or
"pending clarification". The actions field must always contain real,
executable guidance drawn from the protocols.

MODE 2 — GUIDANCE (set mode: "guidance"):
Identify the condition. Give specific actions, dosages, durations, and
referral criteria from the protocols.

RULES:
1. ONLY use information from the protocols. Never invent.
2. NEVER recommend a drug the patient is allergic to.
3. ALL fields (condition, assessment, actions, refer_if, answer) MUST be in the SAME LANGUAGE as the question. Translate protocol content if needed.
4. The "answer" field is a complete, formatted clinical response (assessment, actions, referral criteria, source).
5. In guidance mode: give specific actions with dosages, durations, and danger signs.
6. When screening answers are provided in brackets [...] (e.g. "[fever: no. rash: yes]"), switch to GUIDANCE mode. Give SPECIFIC treatment: drug names, dosages, durations, home care steps. Do NOT give meta-actions like "recommend treatment" — give the actual treatment.
7. The "condition" field must be the clinical condition name (e.g. "Eczema Dermatitis", "Pneumonia"), never the mode name.
8. If the protocols provided do NOT cover the patient's question or condition, say this is outside the scope of available protocols and recommend consulting a supervisor or referring to a facility. Do NOT answer from general medical knowledge.
9. OUTSIDE CHW SCOPE — always respond "This requires a medical professional. Refer to a facility.":
   - Ordering, selecting, or interpreting lab tests (blood work, cultures, urinalysis) — if the question is "what tests to order", refer
   - Interpreting imaging (X-ray, ultrasound, CT)
   - Prescribing controlled substances or medications not in the protocols
   - Surgical procedures, lumbar punctures, intubation, sedation
   - Chemotherapy, radiotherapy, or specialist treatments
   - Adjusting antiretroviral regimens or second-line treatments"""


def consult(
    question: str,
    kb: KnowledgeBase,
    llm_cfg: LLMConfig,
    *,
    history: list[dict[str, str]] | None = None,
    audit: AuditLog | None = None,
    verify: bool = False,
    language: str = "auto",
) -> dict:
    """Answer a clinical question using retrieved protocols.

    Returns:
        dict with keys: answer, sources, confidence, safety_flags, emergency,
        grounded (if verify=True), issues (if verify=True).
    """
    import re as _re
    safety_flags: list[SafetyFlag] = []

    def _flag(f: SafetyFlag) -> None:
        """Append a safety flag if it is not already present.

        Prevents duplicate flags from the multiple code paths that can
        classify the same consult as an emergency (regex fast path,
        preflight vital_emergency, cross-lingual fallback, LLM urgency
        override). Keeping this as a helper instead of scattered
        `if flag not in safety_flags` guards keeps the invariant in one
        place — adding a new emergency path cannot regress the dedup.
        """
        if f not in safety_flags:
            safety_flags.append(f)

    # --- Separate clinical query from triage context for retrieval ---
    search_query = _extract_search_query(question)

    # --- Fast path: regex emergency on raw question (zero LLM cost) ---
    is_emergency, emergency_patterns = detect_emergency(search_query)

    # --- Pre-flight: structured classification (skipped if regex already fired) ---
    pf: dict = {}
    if not is_emergency:
        pf = preflight(search_query, llm_cfg)
        if pf.get("vital_emergency"):
            is_emergency = True

    # --- Out-of-scope short-circuit BEFORE retrieval ---
    if pf.get("out_of_scope"):
        return _out_of_scope_result(
            question,
            reason=pf.get("rejection_reason", ""),
            audit=audit,
        )

    if is_emergency:
        _flag(SafetyFlag.EMERGENCY_DETECTED)

    # --- Retrieval (legacy keyword expansion + preflight terms when available) ---
    # The legacy `_KEYWORDS_PROMPT` is well-tuned for this corpus and is the
    # PRIMARY secondary search. The preflight clinical_terms are an OPTIONAL
    # tertiary supplement that helps surface protocols the legacy expansion
    # misses (e.g. lay-language diabetes triad → polyuria/polydipsia →
    # Gestational Diabetes). Sending both is strictly better than either alone
    # because the merge keeps max score per chunk.
    preflight_terms = " ".join(pf.get("clinical_terms", []))
    results, english_keywords = _multi_query_search(
        kb, search_query, llm_cfg, preflight_terms=preflight_terms,
    )

    # --- Cross-lingual emergency detection via English keywords (legacy fallback) ---
    # Only runs when preflight did NOT execute. When preflight succeeded its
    # `vital_emergency` verdict is authoritative — running regex over its own
    # clinical terms produces false positives (e.g. "bee sting, only local" gets
    # expanded to include "anaphylaxis" → regex hit → wrong urgency).
    if not pf and not is_emergency and english_keywords:
        is_emergency, emergency_patterns = detect_emergency(english_keywords)
        if is_emergency:
            _flag(SafetyFlag.EMERGENCY_DETECTED)

    if not results:
        result = {
            "answer": _REFER_MSG,
            "sources": [],
            "confidence": Confidence.LOW,
            "safety_flags": [SafetyFlag.LOW_CONFIDENCE],
            "emergency": is_emergency,
        }
        if audit:
            audit.log(mode="consult", question=question, **_audit_kwargs(result))
        return result

    # --- Filter by relevance but keep diverse results ---
    best_score = max(r.score for r in results)
    threshold = best_score * 0.03  # low threshold to include differential diagnoses
    relevant = [r for r in results if r.score >= threshold][:6]  # max 6 — fits in 8192 ctx. The FTS-only safety-net pass in _multi_query_search is what surfaces vector-weak chunks; we do not need a wider cap here.
    if not relevant:
        result = {
            "answer": _REFER_MSG,
            "sources": [{"title": r.title, "score": round(r.score, 3), "profile": r.profile}
                        for r in results[:3]],
            "confidence": Confidence.LOW,
            "safety_flags": [SafetyFlag.LOW_CONFIDENCE],
            "emergency": is_emergency,
        }
        if audit:
            audit.log(mode="consult", question=question, **_audit_kwargs(result))
        return result

    # --- Confidence scoring ---
    confidence = score_confidence(
        [{"title": r.title, "score": r.score} for r in relevant],
        relevant,
    )
    if confidence == Confidence.LOW:
        _flag(SafetyFlag.LOW_CONFIDENCE)
        # Short-circuit: don't call LLM with irrelevant protocols
        result = {
            "answer": _REFER_MSG,
            "sources": [{"title": r.title, "score": round(r.score, 3), "profile": r.profile,
                         "chunk_id": r.chunk_id} for r in relevant[:3]],
            "confidence": Confidence.LOW,
            "safety_flags": safety_flags,
            "emergency": is_emergency,
            "urgency": "routine",
            "mode": "guidance",
            "triage_questions": [],
            "condition": "",
            "assessment": "",
            "actions": [],
            "refer_if": [],
            "source_protocol": "",
        }
        if audit:
            audit.log(mode="consult", question=question, **_audit_kwargs(result))
        return result

    # --- Build context and generate ---
    context = "<protocols>\n"
    sources = []
    seen_titles: set[str] = set()
    protocol_texts = []
    for i, r in enumerate(relevant, 1):
        context += f'<protocol id="{i}" source="{r.title}" profile="{r.profile}">\n'
        context += f"{r.text}\n</protocol>\n"
        # Deduplicate sources by title — show each protocol once
        if r.title not in seen_titles:
            sources.append({
                "title": r.title,
                "score": round(r.score, 3),
                "profile": r.profile,
                "chunk_id": r.chunk_id,
            })
            seen_titles.add(r.title)
        protocol_texts.append(r.text)
    context += "</protocols>"

    # If emergency detected, prepend urgent instruction
    system = _SYSTEM_PROMPT
    if is_emergency:
        system = _EMERGENCY_PREFIX + system

    # Resolve response language: config setting > auto-detect from question
    q_lang = language if language != "auto" else _detect_language(question)
    system += f"\n\nLANGUAGE: ALL fields MUST be written in {q_lang}. Protocols are in English — translate as needed."

    # Detect triage answers — force guidance mode via context injection
    has_triage = bool(_re.search(r'\[.+\]\s*$', question))
    if has_triage:
        system += _GUIDANCE_INJECTION

    # Emergency: skip assessment, go straight to guidance with referral
    if is_emergency:
        system += _EMERGENCY_GUIDANCE_INJECTION

    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({
        "role": "user",
        "content": f"{context}\n\n[Respond in {q_lang}]\n{question}",
    })

    schema = _CONSULT_SCHEMA_GUIDANCE if (has_triage or is_emergency) else _CONSULT_SCHEMA
    structured = chat_structured(messages, llm_cfg, schema, "clinical_response")

    # Force guidance mode when triage answers were provided or emergency detected
    if has_triage or is_emergency:
        structured["mode"] = "guidance"
    if is_emergency:
        structured["urgency"] = "emergency"

    # Clean protocol refs from all text fields
    for key in ("condition", "assessment", "next_question", "source"):
        if key in structured and isinstance(structured[key], str):
            structured[key] = _clean_protocol_refs(structured[key])
    if "refer_if" in structured and isinstance(structured["refer_if"], list):
        structured["refer_if"] = [
            _clean_protocol_refs(r) for r in structured["refer_if"]
            if _clean_protocol_refs(r).strip()
        ]

    # If LLM classified as emergency but regex didn't catch it (and mode is
    # still assessment), override: emergencies should never wait for triage.
    llm_urgency = structured.get("urgency", "routine")
    if llm_urgency == "emergency" and structured.get("mode") == "assessment":
        structured["mode"] = "guidance"
        structured["triage_questions"] = []
        if not is_emergency:
            is_emergency = True
        _flag(SafetyFlag.EMERGENCY_DETECTED)

    # In assessment mode, generate triage questions in the user's language
    # Reuse q_lang already resolved from config/detection above
    if structured.get("mode") == "assessment":
        structured["triage_questions"] = _generate_triage_questions(
            structured, llm_cfg, question_language=q_lang,
            original_question=question,
        )

    answer = _format_structured(structured)

    # --- Post-generation safety checks ---

    # Dosage cross-check (fast, no LLM call)
    dosages_ok, unmatched = check_dosages(answer, protocol_texts)
    if not dosages_ok:
        _flag(SafetyFlag.DOSAGE_MENTIONED)
        logger.warning("Unmatched dosages in answer: %s", unmatched)
        answer += (
            "\n\n⚠ **Verify dosages** — some values could not be confirmed "
            "against source protocols. Check with supervisor before administering."
        )

    # Grounding verification (optional — costs an extra LLM call)
    grounded = None
    issues = None
    if verify:
        grounded, issues = verify_grounding(answer, protocol_texts, llm_cfg)
        if not grounded:
            _flag(SafetyFlag.HALLUCINATION_SUSPECTED)
            answer += (
                "\n\n⚠ **Verification warning** — some claims in this response "
                "may not be fully supported by the source protocols. "
                "Consult your supervisor before acting."
            )

    # Combine regex emergency detection with LLM urgency classification
    llm_urgency = structured.get("urgency", "routine")
    if llm_urgency == "emergency":
        is_emergency = True
        _flag(SafetyFlag.EMERGENCY_DETECTED)
    elif llm_urgency == "urgent" and SafetyFlag.EMERGENCY_DETECTED not in safety_flags:
        _flag(SafetyFlag.URGENT_REFERRAL)

    result = {
        "answer": answer,
        "sources": sources,
        "confidence": confidence,
        "safety_flags": safety_flags,
        "emergency": is_emergency,
        "urgency": llm_urgency,
        "mode": structured.get("mode", "guidance"),
        "triage_questions": structured.get("triage_questions", []),
        # Raw structured fields for rich UI rendering
        "condition": structured.get("condition", ""),
        "assessment": structured.get("assessment", ""),
        "actions": structured.get("actions", []),
        "refer_if": structured.get("refer_if", []),
        "source_protocol": structured.get("source", ""),
    }
    if verify:
        result["grounded"] = grounded
        result["issues"] = issues

    # --- Audit log ---
    if audit:
        audit.log(mode="consult", question=question, **_audit_kwargs(result))

    return result


_REFER_MSG = (
    "This question is outside the scope of the available clinical protocols. "
    "This may require specialist knowledge, hospital-level resources, or controlled medications.\n\n"
    "**Next steps:** Consult your supervisor, the nearest doctor, or a hospital formulary "
    "for guidance specific to this case.\n\n"
    "If this is an emergency, **refer the patient immediately** to the nearest health facility."
)

_OUT_OF_SCOPE_MSG = (
    "**Outside CHW scope.** This decision requires a licensed clinician.\n\n"
    "**Next steps:** Refer the patient to the nearest health facility or consult your "
    "supervising clinician. Do not attempt to make this decision from general knowledge."
)


def _out_of_scope_result(
    question: str,
    *,
    reason: str,
    audit: AuditLog | None,
) -> dict:
    """Build the short-circuit response for questions the preflight rejects.

    The user-facing answer is a static string with no variable interpolation —
    this prevents the preflight's `reason` (which can contain words like
    'order', 'CBC', 'request') from leaking into the response and tripping
    hallucination probes. The reason is preserved in the `assessment` field
    for the audit log.
    """
    body = _OUT_OF_SCOPE_MSG
    result = {
        "answer": body,
        "sources": [],
        "confidence": Confidence.LOW,
        "safety_flags": [SafetyFlag.LOW_CONFIDENCE],
        "emergency": False,
        "urgency": "routine",
        "mode": "guidance",
        "triage_questions": [],
        "condition": "",
        "assessment": reason,
        "actions": [],
        "refer_if": [],
        "source_protocol": "",
    }
    if audit:
        audit.log(mode="consult", question=question, **_audit_kwargs(result))
    return result

_EMERGENCY_PREFIX = """\
⚠ EMERGENCY DETECTED in the question. The patient may need URGENT REFERRAL.
Start your response with: **⚠ URGENT — REFER IMMEDIATELY** if any danger signs are present.
Then provide the immediate stabilization steps from the protocol.

"""


_GUIDANCE_INJECTION = """

IMPORTANT: The screening answers are provided in brackets at the end of the question.
You MUST use GUIDANCE mode. Do NOT ask more questions. Give the full clinical recommendation NOW.
Give SPECIFIC treatments with drug names, dosages, and durations from the protocols."""

_EMERGENCY_GUIDANCE_INJECTION = """

EMERGENCY: Danger signs detected. You MUST use GUIDANCE mode — do NOT use assessment mode.
Do NOT ask screening questions. The patient needs IMMEDIATE referral.
Start with: ⚠ REFER IMMEDIATELY to the nearest health facility.
Then give immediate stabilization steps from the protocols while waiting for transport.
If the protocols do not cover this specific condition, still give general stabilization
advice (airway, breathing, positioning, keep warm) and refer."""


_URGENCY_FIELD = {
    "type": "string",
    "enum": ["routine", "urgent", "emergency"],
    "description": "routine = no danger signs, can manage at health post. urgent = needs referral within hours (e.g. severe dehydration, high fever in pregnancy). emergency = life-threatening, refer IMMEDIATELY (e.g. convulsions, not breathing, severe bleeding, eclampsia, shock).",
}

_CONSULT_SCHEMA_GUIDANCE = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["guidance"],
            "description": "Must be guidance — screening is complete.",
        },
        "urgency": _URGENCY_FIELD,
        "condition": {
            "type": "string",
            "description": " The identified condition name (e.g. 'Eczema Dermatitis', 'Contact Dermatitis').",
        },
        "assessment": {
            "type": "string",
            "description": " Clinical reasoning: why you suspect this condition based on symptoms and screening.",
        },
        "actions": {
            "type": "array",
            "items": {"type": "string"},
            "description": " MUST include specific drug name, dose, route, and duration from the protocols (e.g. 'Ceftriaxone 500mg IM single dose'). If treatment requires controlled medication not available at health post, include in refer_if instead. NEVER write meta-actions.",
        },
        "refer_if": {
            "type": "array",
            "items": {"type": "string"},
            "description": " Danger signs requiring immediate referral.",
        },
        "source": {
            "type": "string",
            "description": " Protocol names used",
        },
        "answer": {
            "type": "string",
            "description": "Complete formatted response in the SAME LANGUAGE as all other fields. Complete formatted clinical response including assessment, treatment actions with dosages, referral criteria, and source protocol. This is what the user sees.",
        },
    },
    "required": ["mode", "urgency", "condition", "assessment", "actions", "refer_if", "source", "answer"],
}


_CONSULT_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["assessment", "guidance"],
            "description": "assessment = need more info (ask next question), guidance = enough info to advise",
        },
        "urgency": _URGENCY_FIELD,
        "condition": {
            "type": "string",
            "description": " The suspected condition name (e.g. 'Measles', 'Pneumonia'). In assessment mode, write the differential.",
        },
        "assessment": {
            "type": "string",
            "description": " In guidance mode: why you suspect this condition. In assessment mode: summarize what you know so far. Do NOT ask questions here — questions are handled separately.",
        },
        "actions": {
            "type": "array",
            "items": {"type": "string"},
            "description": " Concrete clinical steps. In guidance mode: MUST include specific drug name, dose, route, and duration from protocols (e.g. 'Ceftriaxone 500mg IM single dose', 'ORS 200ml after each stool'). If treatment requires controlled medication, include in refer_if. NEVER write meta-actions. In assessment mode: what to do while waiting (e.g. 'Keep wound clean and dry').",
        },
        "refer_if": {
            "type": "array",
            "items": {"type": "string"},
            "description": " Danger signs requiring immediate referral.",
        },
        "source": {
            "type": "string",
            "description": " Protocol names used",
        },
        "answer": {
            "type": "string",
            "description": "Complete formatted response in the SAME LANGUAGE as all other fields. In assessment mode: explain what you're evaluating and ask the next question. In guidance mode: complete clinical response with assessment, treatment actions with dosages, referral criteria, and source. This is what the user sees.",
        },
    },
    "required": ["mode", "urgency", "condition", "assessment", "actions", "refer_if", "source", "answer"],
}


def _detect_language(text: str) -> str:
    """Detect language from text using character and word heuristics.

    Returns a language name for use in prompts (e.g. 'Spanish', 'Portuguese').
    No LLM call. Two-pass strategy:
    1. Script/character detection (non-Latin scripts, Spanish/Portuguese diacritics)
    2. Word-boundary markers for Latin-script disambiguation
    """
    import re as _re

    # --- Pass 1: Script/character detection (fast, decisive) ---
    # Non-Latin scripts: unambiguous
    if _re.search(r'[\u0900-\u097F]', text):  # Devanagari
        return "Hindi"
    if _re.search(r'[\u0600-\u06FF]', text):  # Arabic
        return "Arabic"

    # Spanish-specific characters: ñ, ¿, ¡
    has_spanish_chars = bool(_re.search(r'[ñ¿¡]', text))
    # Portuguese-specific characters: ã, õ, ç (when not in French context)
    has_portuguese_chars = bool(_re.search(r'[ãõ]', text))
    # French-specific: ê, ë, î, ï, û, ü, ç + œ, «, »
    has_french_chars = bool(_re.search(r'[êëîïûœ«»]', text))

    # If only one script matches, return immediately
    char_hits = sum([has_spanish_chars, has_portuguese_chars, has_french_chars])
    if char_hits == 1:
        if has_spanish_chars:
            return "Spanish"
        if has_portuguese_chars:
            return "Portuguese"
        if has_french_chars:
            return "French"

    # --- Pass 2: Word markers (for Latin-script without distinctive chars) ---
    text_lower = text.lower()
    _MARKERS = {
        "Spanish": [r"\bel\b", r"\blos\b", r"\blas\b", r"\bdel\b", r"\bpero\b", r"\btiene\b", r"\btengo\b", r"\bmuy\b", r"\btambién\b", r"\bhay\b", r"\bpuede\b", r"\bduele\b", r"\bdesde\b", r"\bhace\b"],
        "Portuguese": [r"\bnão\b", r"\btem\b", r"\bdos\b", r"\bdas\b", r"\bmas\b", r"\bou\b", r"\bela\b", r"\bele\b", r"\bcriança\b", r"\bmuito\b", r"\btambém\b", r"\bpreciso\b", r"\bpode\b", r"\bdeve\b"],
        "French": [r"\ble\b", r"\bles\b", r"\bdes\b", r"\bdu\b", r"\bavec\b", r"\bune\b", r"\best\b", r"\bpas\b", r"\bpour\b", r"\bdans\b", r"\bje\b", r"\bne\b"],
        "Swahili": [r"\bna\b", r"\bya\b", r"\bwa\b", r"\bkwa\b", r"\bni\b", r"\bkatika\b", r"\bana\b", r"\bhana\b"],
    }
    scores = {}
    for lang, patterns in _MARKERS.items():
        scores[lang] = sum(1 for p in patterns if _re.search(p, text_lower))

    # If character detection narrowed it + word scores confirm, use that
    if has_spanish_chars and has_portuguese_chars:
        # Both have diacritics — use word scores to disambiguate
        if scores.get("Spanish", 0) > scores.get("Portuguese", 0):
            return "Spanish"
        if scores.get("Portuguese", 0) > scores.get("Spanish", 0):
            return "Portuguese"
        return "Spanish"  # default for shared diacritics (á, é, ó common in both)

    best = max(scores, key=scores.get) if scores else "English"
    if scores.get(best, 0) == 0:
        return "English"
    if scores[best] == 1:
        tied = [l for l, s in scores.items() if s == scores[best]]
        if len(tied) == 1:
            return best
        return "English"
    return best


def _extract_search_query(question: str) -> str:
    """Strip triage/screening context from question — keep only clinical symptoms for retrieval."""
    import re as _re
    # Remove bracketed triage answers: [answer1: yes. answer2: no]
    clean = _re.sub(r'\s*\[.*?\]\s*$', '', question)
    # Split on "Danger signs checked" or similar separator
    parts = _re.split(
        r'[.;]\s*(?:Danger signs? checked|Screening results|Now give)',
        clean, flags=_re.IGNORECASE,
    )
    clean = parts[0].strip()
    return clean if len(clean) >= 5 else question



_TRIAGE_PROMPT = """\
You generate screening questions for a community health worker.
Write the questions in {language}.

Format each line as a tag followed by the question:
[YN]   for a yes/no question (presence or absence of a sign or symptom)
[TEXT] for a question that needs a typed answer (duration, weight, description)

STRICT RULES — read carefully before generating:

1. Read the ORIGINAL CHW question below, and any PHOTO CONTEXT if present,
   word by word. Build an internal list of every fact the user has already
   stated — including age, weight, sex, pregnancy, symptom duration, symptom
   laterality, presence or absence of specific danger signs, any medication
   visible in a photo, and anything else relevant. Treat paraphrases and
   colloquial wording as facts (they are facts even if the clinical term
   is not used).

2. You MUST NOT generate a question whose answer is already present in the
   original question or photo context. Re-asking a known fact is a failure.

3. Generate 3-4 screening questions that target genuinely missing facts
   needed to classify or treat the condition.

4. Do not number the questions. Do not add preamble, apology, or commentary.
   Do not emit lines like "here are the questions" or "if you provide more
   context". Output ONLY the question lines themselves, one per line.

5. If you find that all critical facts are already present and no screening
   question is genuinely needed, return the single line:
       [YN] NONE

ORIGINAL CHW QUESTION:
{original_question}

Condition under consideration: {condition}
Assessment so far: {assessment}

Now output 3-4 tagged questions (or `[YN] NONE` if nothing is missing):"""


def _generate_triage_questions(
    data: dict,
    llm_cfg: "LLMConfig | None" = None,
    question_language: str = "the same language as the patient's original question",
    original_question: str = "",
) -> list[dict]:
    """Generate triage questions via a fast LLM call.

    Internal fields (assessment, condition) are in English.
    The LLM generates questions in the user's language via question_language param.
    `original_question` is the raw user input (including any photo context) so
    the generator can avoid re-asking facts the user already provided.
    Falls back to basic IMCI questions if the LLM call fails.
    """
    import re as _re
    source = _clean_protocol_refs(data.get("source", "")) or "IMCI"
    condition = data.get("condition", "")
    assessment = data.get("assessment", "")

    if llm_cfg:
        try:
            prompt = _TRIAGE_PROMPT.format(
                assessment=assessment[:300],
                condition=condition,
                language=question_language,
                original_question=original_question[:800] or "(not provided)",
            )
            raw = chat([{"role": "user", "content": prompt}], llm_cfg).strip()
            # Explicit "nothing missing" signal from the model → no triage questions
            if _re.search(r'\[?\s*YN\s*\]?\s*NONE\b', raw, _re.IGNORECASE):
                return []
            questions = []
            for line in raw.split("\n"):
                line = line.strip()
                if not line or len(line) < 8:
                    continue
                # Skip preamble / meta-commentary lines the LLM may still emit
                if _re.search(
                    r'\b(?:here are|here is|these are|screening questions|based on the|'
                    r'if you provide|i can (?:make|generate|help)|specific and relevant|'
                    r'let me know|clinical case)\b',
                    line, _re.IGNORECASE,
                ):
                    continue
                # Parse [YN] or [TEXT] tag from the LLM output
                tag_match = _re.match(r'\[?(YN|TEXT)\]?\s*(.+)', line, _re.IGNORECASE)
                if tag_match:
                    q_type = "yes_no" if tag_match.group(1).upper() == "YN" else "short_answer"
                    q_text = tag_match.group(2).strip()
                else:
                    # No tag — strip numbering and default to yes_no
                    q_text = _re.sub(r'^\d+[\.\)\-]\s*', '', line).strip()
                    q_type = "yes_no"
                if len(q_text) < 5:
                    continue
                # A real triage question must end with a question mark — lines
                # that don't even look like a question are meta-commentary
                if "?" not in q_text:
                    continue
                questions.append({
                    "text": q_text,
                    "type": q_type,
                    "source": source,
                })
                if len(questions) >= 4:
                    break
            if questions:
                return questions
        except Exception:
            logger.debug("Triage question generation failed, using fallback")

    # Fallback: basic IMCI danger sign questions in the configured language
    return _fallback_triage(source, question_language)


# Pre-translated IMCI danger sign questions for fallback
_FALLBACK_TRIAGE = {
    "English": [
        ("What is the patient's age?", "short_answer"),
        ("Can the patient drink or breastfeed?", "yes_no"),
        ("Any convulsions or loss of consciousness?", "yes_no"),
        ("Any signs of severe illness (unable to eat, persistent vomiting)?", "yes_no"),
    ],
    "Spanish": [
        ("¿Cuál es la edad del paciente?", "short_answer"),
        ("¿Puede el paciente beber o amamantar?", "yes_no"),
        ("¿Ha tenido convulsiones o pérdida de conciencia?", "yes_no"),
        ("¿Presenta signos de enfermedad grave (no puede comer, vómitos persistentes)?", "yes_no"),
    ],
    "Portuguese": [
        ("Qual é a idade do paciente?", "short_answer"),
        ("O paciente consegue beber ou amamentar?", "yes_no"),
        ("Houve convulsões ou perda de consciência?", "yes_no"),
        ("Apresenta sinais de doença grave (não consegue comer, vômitos persistentes)?", "yes_no"),
    ],
    "French": [
        ("Quel est l'âge du patient?", "short_answer"),
        ("Le patient peut-il boire ou allaiter?", "yes_no"),
        ("Y a-t-il eu des convulsions ou une perte de conscience?", "yes_no"),
        ("Y a-t-il des signes de maladie grave (incapable de manger, vomissements persistants)?", "yes_no"),
    ],
    "Swahili": [
        ("Mgonjwa ana umri gani?", "short_answer"),
        ("Mgonjwa anaweza kunywa au kunyonya?", "yes_no"),
        ("Kuna degedege au kupoteza fahamu?", "yes_no"),
        ("Kuna dalili za ugonjwa mkubwa (hawezi kula, kutapika sana)?", "yes_no"),
    ],
}


def _fallback_triage(source: str, language: str) -> list[dict]:
    questions = _FALLBACK_TRIAGE.get(language, _FALLBACK_TRIAGE["English"])
    return [
        {"text": text, "type": qtype, "source": source}
        for text, qtype in questions
    ]


def _clean_protocol_refs(text: str) -> str:
    """Remove protocol ID references and LaTeX artifacts that small models inject."""
    import re as _re
    # Remove patterns like: (Protocol 1), (Protocol ID '1'), (Protocolo 7)
    text = _re.sub(r"\s*\(Protocol(?:o)?\s*(?:ID\s*)?'?\d+'?\)", "", text, flags=_re.IGNORECASE)
    # Remove standalone "Protocol X" or "protocol_X" references
    text = _re.sub(r"\bProtocol(?:o)?\s*(?:ID\s*)?'?\d+'?(?:\s*\([^)]*\))?", "", text, flags=_re.IGNORECASE)
    # Remove underscore variants: protocol_1, protocol_2, etc.
    text = _re.sub(r"\bprotocol[_\s]*\d+\b", "", text, flags=_re.IGNORECASE)
    # Clean LaTeX artifacts
    text = _re.sub(r"\\ge(?:q)?\s*", ">=", text)
    text = _re.sub(r"\\le(?:q)?\s*", "<=", text)
    text = _re.sub(r"\\circ", "°", text)
    text = _re.sub(r"\^\{([^}]*)\}", r"\1", text)  # ^{\circ} → °
    text = _re.sub(r"\\times", "×", text)
    text = _re.sub(r"\\pm", "±", text)
    text = _re.sub(r"\\text\{([^}]*)\}", r"\1", text)
    text = _re.sub(r"\$([^$]+)\$", r"\1", text)  # $...$ → ...
    # Remove dangling connectors left after removing protocol refs
    text = _re.sub(r";\s*;", ";", text)
    text = _re.sub(r"\b(?:and|y|e)\s*\d+\b", "", text)  # "y 4", "and 3"
    text = _re.sub(r"^\s*(?:and|y|e)\s+", "", text)  # leading "y "
    text = _re.sub(r"\s+(?:and|y|e)\s*$", "", text)  # trailing " y"
    text = _re.sub(r",\s*(?:and|y|e)\s*,", ",", text)  # ", y ,"
    # Clean up double spaces, trailing semicolons/commas
    text = _re.sub(r"  +", " ", text)
    text = _re.sub(r"\s*[;,]\s*$", "", text)
    return text.strip()


def _format_structured(data: dict) -> str:
    """Format structured JSON response into readable markdown.

    Prefers the LLM-generated 'answer' field (already in the user's language).
    Falls back to formatting from internal English fields if 'answer' is missing.
    """
    import re as _re

    # Prefer LLM-generated answer in user's language
    llm_answer = data.get("answer", "").strip()
    if llm_answer:
        return _clean_protocol_refs(llm_answer)

    # Fallback: format from internal English fields
    mode = data.get("mode", "guidance")
    parts = []

    condition = _clean_protocol_refs(data.get("condition", ""))
    assessment = _clean_protocol_refs(data.get("assessment", ""))

    if mode == "assessment":
        if condition:
            parts.append(f"**Evaluating:** **{condition}**")
        if assessment:
            parts.append(f"{assessment}")

        next_q = _clean_protocol_refs(data.get("next_question", ""))
        if next_q:
            parts.append(f"\n**Next question:**\n{next_q}")

        actions = data.get("actions", [])
        if actions:
            parts.append("\n**While assessing:**")
            for i, a in enumerate(actions, 1):
                cleaned = _re.sub(r"^\s*\d+[\.\)]\s*", "", a)
                parts.append(f"{i}. {_clean_protocol_refs(cleaned)}")

        refer = data.get("refer_if", [])
        if refer:
            parts.append("\n**Refer immediately if:** " + "; ".join(
                _clean_protocol_refs(r) for r in refer))

    else:
        if condition:
            parts.append(f"**Assessment:** **{condition}** — {assessment}")
        else:
            parts.append(f"**Assessment:** {assessment}")

        actions = data.get("actions", [])
        if actions:
            parts.append("**Actions:**")
            for i, a in enumerate(actions, 1):
                cleaned = _re.sub(r"^\s*\d+[\.\)]\s*", "", a)
                parts.append(f"{i}. {_clean_protocol_refs(cleaned)}")

        refer = data.get("refer_if", [])
        if refer:
            parts.append("**Refer if:** " + "; ".join(
                _clean_protocol_refs(r) for r in refer))

        source = _clean_protocol_refs(data.get("source", ""))
        if source:
            parts.append(f"**Source:** {source}")

    return "\n".join(parts)


def _audit_kwargs(result: dict) -> dict:
    """Extract kwargs for AuditLog.log from a result dict."""
    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "confidence": result["confidence"],
        "safety_flags": result.get("safety_flags", []),
        "grounded": result.get("grounded"),
        "issues": result.get("issues"),
        "emergency": result.get("emergency", False),
    }


_KEYWORDS_PROMPT = """\
Rewrite this question using ENGLISH medical terminology for protocol search.
Translate ALL terms to English, regardless of the input language.
Do NOT diagnose — only translate symptoms to clinical search terms.
Example: "baby not breathing after birth" → "newborn apnea birth resuscitation ventilation"
Example: "niño con fiebre y sarpullido" → "pediatric febrile exanthem rash measles"
Example: "secreción uretral purulenta, diplococos gramnegativos" → "urethral discharge gonorrhea STI ceftriaxone"
Example: "pregnant woman convulsions" → "pregnancy seizure eclampsia magnesium sulfate"
Example: "hombre fumigando cultivo, pupilas pequeñas, sudando" → "pesticide poisoning organophosphate cholinergic miosis diaphoresis atropine"
Return ONLY English terms separated by spaces.
Question: """


def _multi_query_search(
    kb: KnowledgeBase,
    question: str,
    llm_cfg: LLMConfig,
    preflight_terms: str = "",
) -> tuple[list[SearchResult], str]:
    """Search with up to three queries and merge by chunk id.

    1. Primary  — raw question (catches the user's exact wording)
    2. Secondary — legacy `_KEYWORDS_PROMPT` LLM expansion (well-tuned for
       this corpus)
    3. Tertiary — preflight clinical_terms when available (per-case clinical
       translation that can surface protocols the legacy expansion misses,
       e.g. lay diabetes triad → "polyuria polydipsia" → Gestational Diabetes)

    All three results are merged by chunk id, keeping the highest score per
    chunk. Failures in any single source are non-fatal.

    Returns:
        Tuple of (top results, secondary english_keywords used by callers
        for downstream emergency regex fallbacks).
    """
    # 1. Primary search — cast wide net on the raw question.
    # top_k=20 is deliberate: the multilingual embedder occasionally fails to
    # place a chunk near the query in vector space even when FTS matches it at
    # rank 1 (e.g. organophosphate poisoning for "pesticide exposure miosis"),
    # so the chunk arrives at RRF-fused rank ~12-14. A wider net lets these
    # FTS-strong but vector-weak chunks survive the per-query cut.
    results = kb.search(question, top_k=20)

    def _merge(extra: list[SearchResult]) -> None:
        seen = {r.chunk_id: i for i, r in enumerate(results)}
        for r in extra:
            if r.chunk_id in seen:
                idx = seen[r.chunk_id]
                if r.score > results[idx].score:
                    results[idx] = r
            else:
                seen[r.chunk_id] = len(results)
                results.append(r)

    # 2. Secondary search — legacy English keyword expansion
    english_keywords = ""
    try:
        english_keywords = chat(
            [{"role": "user", "content": _KEYWORDS_PROMPT + question}],
            llm_cfg,
        ).strip()
        if english_keywords:
            _merge(kb.search(english_keywords, top_k=20))
    except Exception:
        pass

    # 3. Tertiary search — preflight clinical_terms (when supplied)
    if preflight_terms:
        try:
            _merge(kb.search(preflight_terms, top_k=20))
        except Exception:
            pass

    # 4. Safety net — pure FTS/BM25 on the English expansion. Catches chunks
    #    the hybrid retriever drags down because the embedder put their vector
    #    far from the query (e.g. organophosphate for "pesticide exposure").
    #    We keep this small (top_k=5) so it only rescues the top keyword hits.
    if english_keywords:
        try:
            _merge(kb.search(english_keywords, top_k=5, fts_only=True))
        except Exception:
            pass

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:20], english_keywords
