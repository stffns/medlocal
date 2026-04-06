"""Consultation mode — clinical Q&A backed by protocol retrieval."""

from __future__ import annotations

import logging

from .config import LLMConfig, MedLocalConfig
from .knowledge import KnowledgeBase, SearchResult
from .llm import chat, chat_structured
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

You have TWO modes:

MODE 1 — GUIDED ASSESSMENT (when critical information is missing):
If the question describes symptoms but lacks key details needed to classify or treat, do NOT guess.
Instead, ask the NEXT MOST IMPORTANT question from the clinical protocol's decision tree.
Ask ONE question at a time. Explain briefly why you are asking.
Set mode to "assessment".

MODE 2 — CLINICAL GUIDANCE (when you have enough information):
When you have enough details to identify the condition and recommend actions, give the full response.
Set mode to "guidance".

DECISION: Use assessment mode ONLY when critical information is truly missing.
If the user already provided information (e.g. "sin fiebre" = no fever, "hace 2 semanas" = duration 2 weeks), treat it as answered — do NOT ask again.
Only ask about details NOT already mentioned:
- Danger signs not yet addressed
- Age not specified for a child
- Key differentiating symptoms still unknown

Use guidance mode when you can identify the condition AND give specific actions.

RULES:
1. ONLY use information from the protocols. Never invent.
2. NEVER recommend a drug the patient is allergic to.
3. ALL fields (condition, assessment, actions, refer_if, answer) MUST be in the SAME LANGUAGE as the question. Translate protocol content if needed.
4. The "answer" field is a complete, formatted clinical response (assessment, actions, referral criteria, source).
5. In guidance mode: give specific actions with dosages, durations, and danger signs.
6. When screening answers are provided in brackets [...] (e.g. "[fever: no. rash: yes]"), switch to GUIDANCE mode. Give SPECIFIC treatment: drug names, dosages, durations, home care steps. Do NOT give meta-actions like "recommend treatment" — give the actual treatment.
7. The "condition" field must be the clinical condition name (e.g. "Eczema Dermatitis", "Pneumonia"), never the mode name.
8. If the protocols provided do NOT cover the patient's question or condition, say this is outside the scope of available protocols and recommend consulting a supervisor or referring to a facility. Do NOT answer from general medical knowledge."""


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

    # --- Separate clinical query from triage context for retrieval ---
    search_query = _extract_search_query(question)

    # --- Emergency detection on clinical query (not triage answers) ---
    is_emergency, emergency_patterns = detect_emergency(search_query)
    if is_emergency:
        safety_flags.append(SafetyFlag.EMERGENCY_DETECTED)

    # --- Retrieval (use clean query, not triage answers) ---
    results, english_keywords = _multi_query_search(kb, search_query, llm_cfg)

    # --- Cross-lingual emergency detection via English keywords ---
    # The keyword expansion translates any language to English clinical terms,
    # so we can catch danger signs that regex missed in the original language.
    if not is_emergency and english_keywords:
        is_emergency, emergency_patterns = detect_emergency(english_keywords)
        if is_emergency:
            safety_flags.append(SafetyFlag.EMERGENCY_DETECTED)

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
    relevant = [r for r in results if r.score >= threshold][:4]  # max 4 — less noise for small models
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
        safety_flags.append(SafetyFlag.LOW_CONFIDENCE)
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
            safety_flags.append(SafetyFlag.EMERGENCY_DETECTED)

    # In assessment mode, generate triage questions in the user's language
    # Reuse q_lang already resolved from config/detection above
    if structured.get("mode") == "assessment":
        structured["triage_questions"] = _generate_triage_questions(
            structured, llm_cfg, question_language=q_lang,
        )

    answer = _format_structured(structured)

    # --- Post-generation safety checks ---

    # Dosage cross-check (fast, no LLM call)
    dosages_ok, unmatched = check_dosages(answer, protocol_texts)
    if not dosages_ok:
        safety_flags.append(SafetyFlag.DOSAGE_MENTIONED)
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
            safety_flags.append(SafetyFlag.HALLUCINATION_SUSPECTED)
            answer += (
                "\n\n⚠ **Verification warning** — some claims in this response "
                "may not be fully supported by the source protocols. "
                "Consult your supervisor before acting."
            )

    # Combine regex emergency detection with LLM urgency classification
    llm_urgency = structured.get("urgency", "routine")
    if llm_urgency == "emergency":
        is_emergency = True
        if SafetyFlag.EMERGENCY_DETECTED not in safety_flags:
            safety_flags.append(SafetyFlag.EMERGENCY_DETECTED)
    elif llm_urgency == "urgent" and SafetyFlag.EMERGENCY_DETECTED not in safety_flags:
        safety_flags.append(SafetyFlag.URGENT_REFERRAL)

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
Generate 3-4 screening questions for this clinical case.
Write the questions in {language}.

Format each line as: [YN] or [TEXT] followed by the question.
[YN] = yes/no question (danger signs, symptoms present/absent)
[TEXT] = needs a typed answer (age, duration, weight, description)

Example:
[TEXT] What is the patient's age?
[YN] Does the patient have fever?
[YN] Can the patient drink fluids?
[TEXT] How long has the rash been present?

Assessment: {assessment}
Condition: {condition}
Questions:"""


def _generate_triage_questions(
    data: dict,
    llm_cfg: "LLMConfig | None" = None,
    question_language: str = "the same language as the patient's original question",
) -> list[dict]:
    """Generate triage questions via a fast LLM call.

    Internal fields (assessment, condition) are in English.
    The LLM generates questions in the user's language via question_language param.
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
            )
            raw = chat([{"role": "user", "content": prompt}], llm_cfg).strip()
            questions = []
            for line in raw.split("\n"):
                line = line.strip()
                if not line or len(line) < 8:
                    continue
                # Skip preamble lines the LLM adds before actual questions
                if _re.search(r'\b(?:here are|screening questions|based on the)\b', line, _re.IGNORECASE):
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
                questions.append({
                    "text": q_text if q_text.endswith("?") else q_text + "?",
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
Return ONLY English terms separated by spaces.
Question: """


def _multi_query_search(
    kb: KnowledgeBase, question: str, llm_cfg: LLMConfig,
) -> tuple[list[SearchResult], str]:
    """Search with original question + LLM-expanded clinical terms.

    Returns:
        Tuple of (results, english_keywords). Keywords are the English clinical
        terms generated for secondary search (useful for language-independent
        emergency detection).
    """
    # Primary search — cast wide net
    results = kb.search(question, top_k=10)
    english_keywords = ""

    # Generate clinical keywords for secondary search
    try:
        english_keywords = chat(
            [{"role": "user", "content": _KEYWORDS_PROMPT + question}],
            llm_cfg,
        ).strip()
        secondary = kb.search(english_keywords, top_k=10)

        # Merge: deduplicate by chunk_id, keep higher score
        seen = {r.chunk_id: i for i, r in enumerate(results)}
        for r in secondary:
            if r.chunk_id in seen:
                idx = seen[r.chunk_id]
                if r.score > results[idx].score:
                    results[idx] = r  # upgrade score
            else:
                seen[r.chunk_id] = len(results)
                results.append(r)
    except Exception:
        pass  # Fall back to primary results only

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:7], english_keywords
