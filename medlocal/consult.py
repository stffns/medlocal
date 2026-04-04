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
Read ALL protocols provided. Your answer should be a practical GUIDE — not a glossary.

RULES:
1. ONLY use information from the protocols. Never invent medical information.
2. Be a GUIDE: explain what to look for, what to do, and why each step matters.
3. Include dosages with weight/age ranges when the protocol provides them.
4. NEVER suggest a drug the patient is allergic to.
5. CRITICAL: Respond in the SAME LANGUAGE as the question. If the question is in Amharic, respond in Amharic. If in French, respond in French. If in Spanish, respond in Spanish. The field labels (condition, assessment, actions) stay in that language too.
6. Always ask about vaccination status for children with fever + rash.
7. BEFORE recommending any medication, your ask_also MUST include: "Any known drug allergies?" This is mandatory whenever antibiotics, antimalarials, or any medication is recommended.
8. When the query describes symptoms without confirmation, ask_also should include the key questions needed to confirm the diagnosis BEFORE treating.

Respond with a JSON object following the provided schema. For each field:
- condition: Name the suspected condition (e.g. "Measles", not "Measles Who")
- assessment: Explain WHY you suspect this — what symptoms match the protocol
- actions: Step-by-step guide with specifics (dosages, durations, what to watch for)
- refer_if: Danger signs that mean the patient needs a hospital NOW
- ask_also: Critical questions the health worker should ask the patient/caregiver"""


def consult(
    question: str,
    kb: KnowledgeBase,
    llm_cfg: LLMConfig,
    *,
    history: list[dict[str, str]] | None = None,
    audit: AuditLog | None = None,
    verify: bool = False,
) -> dict:
    """Answer a clinical question using retrieved protocols.

    Returns:
        dict with keys: answer, sources, confidence, safety_flags, emergency,
        grounded (if verify=True), issues (if verify=True).
    """
    safety_flags: list[SafetyFlag] = []

    # --- Emergency detection on the question itself ---
    is_emergency, emergency_patterns = detect_emergency(question)
    if is_emergency:
        safety_flags.append(SafetyFlag.EMERGENCY_DETECTED)

    # --- Retrieval ---
    results = _multi_query_search(kb, question, llm_cfg)

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
    relevant = [r for r in results if r.score >= threshold][:5]  # max 5 to avoid confusion
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

    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({
        "role": "user",
        "content": f"{context}\n\n{question}",
    })

    structured = chat_structured(messages, llm_cfg, _CONSULT_SCHEMA, "clinical_response")
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

    result = {
        "answer": answer,
        "sources": sources,
        "confidence": confidence,
        "safety_flags": safety_flags,
        "emergency": is_emergency,
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


_CONSULT_SCHEMA = {
    "type": "object",
    "properties": {
        "condition": {
            "type": "string",
            "description": "The suspected condition name only (e.g. 'Measles', 'Severe malaria', 'Pre-eclampsia'). NOT the protocol name.",
        },
        "assessment": {
            "type": "string",
            "description": "One sentence explaining WHY this condition is suspected based on the symptoms described",
        },
        "actions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Step-by-step clinical actions. Include dosages, durations, and what to observe. Each step should be actionable and specific.",
        },
        "refer_if": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Danger signs requiring immediate referral to hospital. Be specific about what to look for.",
        },
        "source": {
            "type": "string",
            "description": "Protocol names used in the answer",
        },
        "ask_also": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Critical questions the health worker should ask the patient or caregiver to improve the assessment. Always include vaccination status for children.",
        },
    },
    "required": ["condition", "assessment", "actions", "refer_if", "source"],
}


def _format_structured(data: dict) -> str:
    """Format structured JSON response into readable markdown."""
    parts = []
    condition = data.get("condition", "")
    assessment = data.get("assessment", "")
    if condition:
        parts.append(f"**Assessment:** **{condition}** — {assessment}")
    else:
        parts.append(f"**Assessment:** {assessment}")

    actions = data.get("actions", [])
    if actions:
        parts.append("**Actions:**")
        for i, a in enumerate(actions, 1):
            # Strip leading numbers/bullets that the model may inject (e.g. "1. ", "- ")
            import re as _re
            cleaned = _re.sub(r"^\s*\d+[\.\)]\s*", "", a)
            parts.append(f"{i}. {cleaned}")

    refer = data.get("refer_if", [])
    if refer:
        parts.append("**Refer if:** " + "; ".join(refer))

    source = data.get("source", "")
    if source:
        parts.append(f"**Source:** {source}")

    ask = data.get("ask_also", [])
    if ask:
        parts.append("**Ask also:** " + " ".join(ask))

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
Rewrite this question using medical terminology for the symptoms described. Do NOT diagnose.
Only translate lay terms to clinical terms.
Example: "baby not breathing after birth" → "newborn apnea birth resuscitation ventilation"
Example: "child fever rash red eyes" → "pediatric febrile exanthem conjunctivitis maculopapular rash"
Example: "chest pain sweating" → "chest pain diaphoresis acute cardiac"
Example: "pregnant woman convulsions" → "pregnancy seizure antepartum convulsion"
Return ONLY the terms separated by spaces.
Question: """


def _multi_query_search(
    kb: KnowledgeBase, question: str, llm_cfg: LLMConfig,
) -> list[SearchResult]:
    """Search with original question + LLM-expanded clinical terms."""
    # Primary search — cast wide net
    results = kb.search(question, top_k=10)

    # Generate clinical keywords for secondary search
    try:
        keywords = chat(
            [{"role": "user", "content": _KEYWORDS_PROMPT + question}],
            llm_cfg,
        ).strip()
        secondary = kb.search(keywords, top_k=10)

        # Merge and deduplicate by chunk_id
        seen = {r.chunk_id for r in results}
        for r in secondary:
            if r.chunk_id not in seen:
                results.append(r)
                seen.add(r.chunk_id)
    except Exception:
        pass  # Fall back to primary results only

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:7]
