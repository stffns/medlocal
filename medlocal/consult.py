"""Consultation mode — clinical Q&A backed by protocol retrieval."""

from __future__ import annotations

import logging

from .config import LLMConfig, MedLocalConfig
from .knowledge import KnowledgeBase, SearchResult
from .llm import StructuredLLMParseError, chat, chat_structured
from .preflight import preflight
from .runtime_check import RuntimePreconditionError, check_runtime_or_raise
from .safety import (
    AuditLog,
    Confidence,
    SafetyFlag,
    check_allergies_in_answer,
    check_controlled_drugs,
    check_dosages,
    detect_emergency,
    extract_allergies,
    score_confidence,
    verify_grounding,
)

# Process-level flag: run the LM Studio runtime check once per Python
# process (not once per query). The cost is one HTTP GET at startup
# and zero thereafter. The check is zero-cost on non-LM-Studio
# backends (Ollama, Gemini, OpenAI) because it short-circuits when
# the base_url is not localhost.
_runtime_checked: bool = False

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a clinical decision support assistant for community health workers (CHWs).
Read ALL protocols provided. ALL output MUST be in the SAME LANGUAGE as the question.

PRIORITY 0 — CONTRAINDICATION SCAN (runs BEFORE everything else)
Scan the question for a drug name. If found, check the protocols for any
contraindication matching that drug + the patient's stated characteristics
(age, weight, pregnancy, allergy, comorbidity). If a match exists:
  - STOP. Ignore every other protocol. Your entire response is:
  - mode = "guidance", urgency = "routine"
  - assessment = one sentence: "[Drug] is contraindicated in [patient]
    because [reason]. Use [alternative] instead."
    Never write "insufficient data" — the contraindication is the answer.
  - actions (exactly 2-3):
    1. Name the drug and state why it cannot be given to this patient.
    2. Give the protocol-approved alternative with its dose.
    3. (Optional) If the alternative needs one fact (e.g. weight), ask here.
  - Do NOT add referral lists, danger signs, or content from other protocols.
  - Never refuse a drug AND compute its dose in the same response.

PRIORITY 0.5 — CONTROLLED / SPECIALIST DRUG SCAN
CHWs cannot dose: opioids, sedatives/anaesthetics, chemotherapy,
second-line ARVs, parenteral vancomycin/aminoglycosides, immunosuppressants,
insulin sliding-scale. If asked → refuse naming the drug, suggest a CHW-level
alternative, include an explicit referral. In the refusal text do NOT use
the words "dose", "mg", or "calculate" — say "use of this drug" instead.

MODE SELECTION
Extract every fact the user already stated (age, symptoms, duration,
negations, prior treatment). Match meaning across languages.
Then pick mode:
  A. Contraindication or safety refusal found → guidance mode.
  B. Enough facts for a protocol treatment path → guidance mode.
     "Enough facts" means the user stated BOTH:
     (1) a specific condition or clear symptoms, AND
     (2) enough patient info to select a protocol path.
     If the user asks about dosing but does NOT name a specific drug
     or condition, you do NOT have enough facts — use assessment mode.
  C. Any critical fact genuinely missing → assessment mode: ask ONE question.
     Missing facts include: which drug, which condition, what symptoms,
     pregnancy status when relevant, allergies when prescribing.
     IMPORTANT: if the user asks about dosing or treatment but does NOT
     state a condition, symptoms, or specific drug name, you MUST use
     assessment mode and ask what they need treatment for. Do NOT guess
     a condition from the retrieved protocols.

ASSESSMENT MODE
Ask ONE question about the single most important missing fact.
Even in assessment, if the situation is urgent or a danger sign is present,
your actions MUST include the referral instruction and immediate care steps
from the protocol — never leave actions empty or with placeholders.

GUIDANCE MODE
Identify the condition. Give specific actions: drug name, dose, route,
duration, and referral criteria — all from the protocols.

RULES
1. ONLY use protocol information. Never invent.
2. NEVER recommend a drug the patient is allergic to.
3. Screening answers in brackets [...] → switch to guidance mode immediately.
4. Condition field = clinical name, never the mode name.
5. If protocols do not cover the question → say so and refer. No general knowledge.
6. OUTSIDE CHW SCOPE — always refer: lab tests, imaging, controlled substances,
   surgery, specialist treatments, ARV adjustments."""


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

    # --- Runtime precondition check (once per process) ---
    # Verifies LM Studio is loaded with the required context length
    # BEFORE any expensive LLM work. Catches the "n_ctx=4096 default
    # auto-load" gotcha that burned hours on 2026-04-07 and 2026-04-08.
    # Fails loud with an actionable error — no silent truncation
    # at case 80 of the benchmark.
    global _runtime_checked
    if not _runtime_checked:
        try:
            info = check_runtime_or_raise(llm_cfg)
            if info:
                logger.info(
                    "Runtime check OK: %s ctx=%d",
                    info.model_id, info.loaded_context_length,
                )
        except RuntimePreconditionError as exc:
            # Do NOT swallow — re-raise so the caller (CLI, bench,
            # smoke, API) gets a clear message and exits cleanly.
            logger.error("Runtime precondition failed:\n%s", exc)
            raise
        _runtime_checked = True

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

    # --- Defense-in-depth: re-run the emergency regex on the preflight's
    # English clinical_terms translation. This catches the failure mode
    # where a smaller model (E2B) reasons its way to vital_emergency=False
    # on a case whose translated keywords would unambiguously match the
    # regex ("cleaning product ingestion child", "chest indrawing",
    # "facial deep wound child"). Architectural rationale: the raw-question
    # regex is the zero-LLM fast path, the preflight LLM is the semantic
    # classifier, and THIS pass is the "trust the translation the preflight
    # already produced" safety net. Credit to Jay's observation on
    # 2026-04-08: if we bother translating, we should bother validating
    # the translation.
    if not is_emergency and pf.get("clinical_terms"):
        english_probe = " ".join(pf["clinical_terms"])
        backup_em, backup_patterns = detect_emergency(english_probe)
        if backup_em:
            is_emergency = True
            emergency_patterns = backup_patterns
            logger.info(
                "Emergency caught by regex-over-preflight-translation: "
                "query=%r terms=%r patterns=%r",
                search_query[:80], english_probe[:80], backup_patterns,
            )

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
    relevant = [r for r in results if r.score >= threshold][:4]  # max 4 — keeps total prompt under 8192 ctx and reduces protocol mixing
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

    # PRIORITY 0 — allergy extraction. Runs BEFORE the LLM call. If the
    # user reported any drug allergy in the question, we inject a hard
    # constraint into the system prompt naming every allergen and every
    # class sibling. The same list is used later as a post-process guard
    # to override the answer if the model slipped. This closes the E2B
    # ST04 non-deterministic failure mode on "fever + allergy to X".
    reported_allergies = extract_allergies(question)
    if reported_allergies:
        logger.info("consult: allergies extracted from question: %s", reported_allergies)

    # If emergency detected, prepend urgent instruction
    system = _SYSTEM_PROMPT
    if is_emergency:
        system = _EMERGENCY_PREFIX + system
    if reported_allergies:
        allergy_block = (
            "\n\n═══════════════════════════════════════════════════════════════════════\n"
            "PRIORITY 0 — USER-REPORTED DRUG ALLERGY (HARD CONSTRAINT)\n"
            "═══════════════════════════════════════════════════════════════════════\n"
            f"The patient is ALLERGIC to: {', '.join(reported_allergies)}.\n\n"
            "You MUST NOT recommend ANY of these drugs, in any dose, route, "
            "formulation, brand name, or combination, for ANY reason, "
            "including as examples or alternatives. This also blocks every "
            "class sibling: an allergy to penicillin blocks amoxicillin, "
            "ampicillin, and all other beta-lactams; an allergy to sulfa "
            "blocks cotrimoxazole; an allergy to paracetamol blocks "
            "acetaminophen and brand names like Tylenol or Panadol.\n\n"
            "If the protocol's default treatment is an allergic drug, you "
            "MUST:\n"
            "  1. State explicitly that the default treatment cannot be "
            "given because of the reported allergy.\n"
            "  2. Offer a non-allergic alternative from the retrieved "
            "protocols (see drug-allergies-alternatives.md). If no safe "
            "alternative exists in the CHW scope, recommend REFERRAL.\n"
            "  3. Name the allergic drug in your response so the CHW sees "
            "you processed the allergy.\n"
            "  4. Never provide the dose of an allergic drug, even in a "
            "teaching or pedagogical context.\n"
        )
        system += allergy_block

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

    # Vague query detection: if the preflight terms contain only
    # demographics (age, weight, child, adult) without any symptom,
    # condition, or drug name, force assessment mode — the user hasn't
    # stated what they need treatment for.
    _DEMOGRAPHIC_ONLY = {"child", "infant", "baby", "adult", "pediatric",
                         "neonatal", "neonate", "weight", "age", "year",
                         "years", "month", "months", "kg", "pregnant",
                         "pregnancy", "dosage", "dose", "dosing"}
    pf_terms_set = {t.lower() for t in pf.get("clinical_terms", [])}
    has_clinical_content = bool(pf_terms_set - _DEMOGRAPHIC_ONLY)
    force_assessment = not has_clinical_content and not has_triage and not is_emergency
    if force_assessment:
        system += "\n\nThe user has NOT stated a condition, symptoms, or drug name. You MUST use assessment mode and ask what they need treatment for. Do NOT guess from the protocols."
        logger.info("consult: vague query detected (no clinical terms beyond demographics) — forcing assessment")

    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({
        "role": "user",
        "content": f"{context}\n\n[Respond in {q_lang}]\n{question}",
    })

    schema = _CONSULT_SCHEMA_GUIDANCE if (has_triage or is_emergency) else _CONSULT_SCHEMA
    try:
        structured = chat_structured(messages, llm_cfg, schema, "clinical_response")
    except StructuredLLMParseError as parse_err:
        # Graceful refusal — the LLM produced output that could not be
        # parsed even after structural repair. Silently returning an
        # empty dict (the pre-2026-04-08 behaviour) is unsafe because
        # the downstream safety layer has nothing to inspect and the
        # audit log records a "successful" empty consult. We instead
        # return an explicit refusal that the CHW can act on.
        logger.error(
            "consult: chat_structured failed, returning GENERATION_FAILED refusal: %s",
            parse_err.reason,
        )
        _flag(SafetyFlag.GENERATION_FAILED)
        _flag(SafetyFlag.LOW_CONFIDENCE)
        refusal = (
            "⚠ The system could not generate a complete response for this "
            "question. This is a technical failure, not a clinical decision. "
            "Please rephrase the question or consult your supervisor."
        )
        result = {
            "answer": refusal,
            "sources": sources,
            "confidence": Confidence.LOW,
            "safety_flags": safety_flags,
            "emergency": is_emergency,
            "urgency": "emergency" if is_emergency else "routine",
            "mode": "guidance",
            "triage_questions": [],
            "condition": "",
            "assessment": refusal,
            "actions": [refusal],
            "refer_if": [],
            "source_protocol": "",
        }
        if audit:
            audit.log(mode="consult_generation_failed",
                      question=question, **_audit_kwargs(result))
        return result

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

    # Controlled / specialist drug guard — defense in depth behind the
    # PRIORITY 0.5 prompt rule. If the LLM computed a dose for an opioid,
    # sedative, anaesthetic, chemo agent, or similar specialist drug, we
    # OVERWRITE the answer with a hard refusal rather than shipping it.
    # This is the check `check_dosages` cannot make — it only validates
    # dose VALUES, not dose AUTHORITY. See Silt's review on 2026-04-08.
    controlled_ok, controlled_violations = check_controlled_drugs(answer)
    if not controlled_ok:
        _flag(SafetyFlag.CONTROLLED_DRUG_DOSE_COMPUTED)
        logger.error(
            "PRIORITY 0.5 bypassed by LLM — controlled drug dose computed: %s",
            controlled_violations,
        )
        violated_drugs = ", ".join(sorted({v.split(":", 1)[1] for v in controlled_violations}))
        refusal = (
            f"⚠ Safety override — this question would have returned a dose for "
            f"a controlled / specialist drug ({violated_drugs}) that is outside "
            f"the CHW scope. Do NOT administer. The appropriate action is to "
            f"refer the patient to a clinician for pain, sedation, or specialist "
            f"management. If the patient is in severe distress, refer urgently."
        )
        answer = refusal
        # Also overwrite the structured fields the UI reads, so the
        # banner is not contradicted by a leftover action list.
        structured["condition"] = (
            structured.get("condition", "") + " — SAFETY OVERRIDE"
        ).strip(" —")
        structured["assessment"] = refusal
        structured["actions"] = [refusal]
        structured["refer_if"] = [
            "Severe pain or symptoms requiring the specialist drug in question."
        ]

    # Allergy guard — defense in depth behind the PRIORITY 0 allergy
    # prompt rule. If the LLM recommended a drug the user said the
    # patient is allergic to, we OVERWRITE the answer with a hard
    # refusal. Unlike the controlled-drug guard (which only fires when
    # a dose token is within range), this fires on ANY mention of the
    # allergen outside a refusal context. The E2B ST04 failure showed
    # the small model sometimes ignores allergy context entirely; this
    # is the hardwired backstop. See `extract_allergies` in safety.py.
    if reported_allergies:
        allergy_ok, allergy_violations = check_allergies_in_answer(
            answer, reported_allergies
        )
        if not allergy_ok:
            _flag(SafetyFlag.ALLERGY_VIOLATION)
            logger.error(
                "PRIORITY 0 allergy guard tripped — LLM recommended "
                "allergic drug despite hard constraint: %s",
                allergy_violations,
            )
            violated = ", ".join(sorted({v.split(":", 1)[0] for v in allergy_violations}))
            refusal = (
                f"⚠ Safety override — the patient is allergic to {violated}. "
                f"The recommended treatment would have included this drug, "
                f"which the safety layer has blocked. Do NOT administer any "
                f"drug from this class. Refer the patient urgently for "
                f"evaluation of a safe alternative. If the protocol has a "
                f"non-allergic alternative (see drug-allergies-alternatives "
                f"protocol), use that instead after discussing with your "
                f"supervisor."
            )
            answer = refusal
            structured["condition"] = (
                structured.get("condition", "") + " — ALLERGY OVERRIDE"
            ).strip(" —")
            structured["assessment"] = refusal
            structured["actions"] = [refusal]
            structured["refer_if"] = [
                f"Reported allergy to {violated} — refer for safe alternative.",
            ]

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
    # Each language list mixes function words (very common, broad coverage)
    # with content words (distinctive but rarer). The Spanish list was too
    # narrow before 2026-04-09 — it only had nouns and verbs, so a clinical
    # phrase like "Mancha roja en la pierna sin dolor ni fiebre" scored 0
    # because none of the existing markers matched, and the single
    # collision "ni" (Spanish negation) lit up the Swahili list (where
    # "ni" means "is/are"), making the auto-detector return Swahili for
    # plain Spanish input. Two fixes here:
    #   1. Broaden Spanish with function words ("en", "la", "sin", "con",
    #      "al", "se", "ni") so common clinical phrasings hit ≥3 markers.
    #   2. Drop "ni" from the Swahili list — it is the only marker that
    #      collides directly with a Spanish word and the remaining seven
    #      Swahili markers still catch the benchmark cases (XE04
    #      "Mtoto hawezi kunywa, ana degedege" hits "ana"; ML03 "Mtoto
    #      ana homa kali na kutapika, hawezi kunywa" hits "ana" + "na").
    text_lower = text.lower()
    _MARKERS = {
        "Spanish": [
            r"\bel\b", r"\blos\b", r"\blas\b", r"\bdel\b", r"\bpero\b",
            r"\btiene\b", r"\btengo\b", r"\bmuy\b", r"\btambién\b", r"\bhay\b",
            r"\bpuede\b", r"\bduele\b", r"\bdesde\b", r"\bhace\b",
            # function words (added 2026-04-09 to fix the Mancha-roja case)
            r"\ben\b", r"\bla\b", r"\bsin\b", r"\bcon\b", r"\bal\b",
            r"\bse\b", r"\bni\b", r"\bque\b", r"\bcomo\b", r"\bpor\b",
        ],
        "Portuguese": [r"\bnão\b", r"\btem\b", r"\bdos\b", r"\bdas\b", r"\bmas\b", r"\bou\b", r"\bela\b", r"\bele\b", r"\bcriança\b", r"\bmuito\b", r"\btambém\b", r"\bpreciso\b", r"\bpode\b", r"\bdeve\b"],
        "French": [r"\ble\b", r"\bles\b", r"\bdes\b", r"\bdu\b", r"\bavec\b", r"\bune\b", r"\best\b", r"\bpas\b", r"\bpour\b", r"\bdans\b", r"\bje\b", r"\bne\b"],
        "Swahili": [r"\bna\b", r"\bya\b", r"\bwa\b", r"\bkwa\b", r"\bkatika\b", r"\bana\b", r"\bhana\b", r"\bmtoto\b", r"\bhoma\b", r"\bkunywa\b"],
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
Rewrite this clinical question as ENGLISH search terms for WHO/MSF protocols.
Translate all terms. Do NOT diagnose — only translate what the user said.
If a drug + population is mentioned, include the safety concern keyword.
"niño con fiebre y sarpullido" → "pediatric febrile exanthem rash measles"
"puedo darle aspirina a un niño con fiebre" → "aspirin child fever contraindicated Reye syndrome"
"hombre fumigando, pupilas pequeñas, sudando" → "pesticide organophosphate cholinergic miosis atropine"
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

    # 3b. Drug-safety boost — if the query names a common drug, run an
    # extra FTS pass with the drug name + "contraindicated" + known safety
    # keywords. This is deterministic (no LLM dependency) and ensures
    # contraindication protocols surface even when the LLM keyword
    # expansion omits safety terms. Fixes non-deterministic aspirin/Reye.
    import re as _re_drugs
    _DRUG_SAFETY = {
        _re_drugs.compile(r"\b(?:aspirin[ae]?)\b", _re_drugs.IGNORECASE):
            "aspirin child Reye contraindicated fever",
        _re_drugs.compile(r"\b(?:ibuprofen[oa]?)\b", _re_drugs.IGNORECASE):
            "ibuprofen infant contraindicated age fever",
        _re_drugs.compile(r"\b(?:paracetamol|acetaminoph[eé]n)\b", _re_drugs.IGNORECASE):
            "paracetamol acetaminophen overdose hepatotoxicity dosage weight",
        _re_drugs.compile(r"\b(?:metformin[ae]?)\b", _re_drugs.IGNORECASE):
            "metformin diabetes contraindicated kidney",
        _re_drugs.compile(r"\b(?:enalapril)\b", _re_drugs.IGNORECASE):
            "enalapril ACE inhibitor contraindicated pregnancy",
    }
    for pattern, safety_terms in _DRUG_SAFETY.items():
        if pattern.search(question):
            try:
                _merge(kb.search(safety_terms, top_k=5, fts_only=True))
            except Exception:
                pass
            break  # one drug match is enough

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
