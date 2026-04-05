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

DECISION: Use assessment mode when ANY of these are missing:
- Danger signs not checked (can the patient drink? convulsions? consciousness?)
- Age not specified for a child (dosages depend on age/weight)
- Duration of symptoms unknown
- Key differentiating symptoms not asked (e.g., fever+rash but no mention of red eyes or vaccination status)

Use guidance mode when you can confidently identify the condition AND give specific actions.

RULES:
1. ONLY use information from the protocols. Never invent.
2. NEVER recommend a drug the patient is allergic to.
3. Respond in the SAME LANGUAGE as the question.
4. In assessment mode: ask ONE question, explain why, and what the possible answers mean.
5. In guidance mode: give specific actions with dosages, durations, and danger signs."""


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
        "mode": structured.get("mode", "guidance"),
        "triage_questions": structured.get("triage_questions", []),
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
        "mode": {
            "type": "string",
            "enum": ["assessment", "guidance"],
            "description": "assessment = need more info (ask next question), guidance = enough info to advise",
        },
        "condition": {
            "type": "string",
            "description": "The suspected condition name (e.g. 'Measles', 'Pneumonia'). In assessment mode, write 'Evaluating' or the differential.",
        },
        "assessment": {
            "type": "string",
            "description": "In guidance mode: why you suspect this condition. In assessment mode: what you know so far and what is missing.",
        },
        "next_question": {
            "type": "string",
            "description": "In assessment mode: the ONE next question to ask. Empty in guidance mode.",
        },
        "triage_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The clinical question to ask"},
                    "type": {"type": "string", "enum": ["yes_no", "short_answer"], "description": "yes_no for tappable buttons, short_answer for text input"},
                    "if_yes": {"type": "string", "description": "What it means if answer is yes"},
                    "if_no": {"type": "string", "description": "What it means if answer is no"},
                    "source": {"type": "string", "description": "Protocol this question comes from"},
                },
                "required": ["text", "type"],
            },
            "description": "In assessment mode: 2-4 focused clinical questions from the decision tree. Each has type (yes_no or short_answer) and consequence. Empty in guidance mode.",
        },
        "actions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "In guidance mode: step-by-step clinical actions with dosages. In assessment mode: immediate actions to take while assessing (e.g. check danger signs).",
        },
        "refer_if": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Danger signs requiring immediate referral.",
        },
        "source": {
            "type": "string",
            "description": "Protocol names used",
        },
    },
    "required": ["mode", "condition", "assessment", "actions", "refer_if", "source"],
}


def _clean_protocol_refs(text: str) -> str:
    """Remove protocol ID references that small models inject."""
    import re as _re
    # Remove patterns like: (Protocol 1), (Protocol ID '1'), (Protocolo 7)
    text = _re.sub(r"\s*\(Protocol(?:o)?\s*(?:ID\s*)?'?\d+'?\)", "", text, flags=_re.IGNORECASE)
    # Remove standalone "Protocol X" references
    text = _re.sub(r"\bProtocol(?:o)?\s*(?:ID\s*)?'?\d+'?(?:\s*\([^)]*\))?", "", text, flags=_re.IGNORECASE)
    # Clean up double spaces
    text = _re.sub(r"  +", " ", text).strip()
    return text


def _format_structured(data: dict) -> str:
    """Format structured JSON response into readable markdown."""
    import re as _re
    mode = data.get("mode", "guidance")
    parts = []

    condition = _clean_protocol_refs(data.get("condition", ""))
    assessment = _clean_protocol_refs(data.get("assessment", ""))

    if mode == "assessment":
        # Guided assessment mode — asking questions
        if condition:
            parts.append(f"**Evaluating:** **{condition}**")
        if assessment:
            parts.append(f"{assessment}")

        # The key question
        next_q = _clean_protocol_refs(data.get("next_question", ""))
        if next_q:
            parts.append(f"\n**Next question:**\n{next_q}")

        # Immediate actions while assessing
        actions = data.get("actions", [])
        if actions:
            parts.append("\n**While assessing:**")
            for i, a in enumerate(actions, 1):
                cleaned = _re.sub(r"^\s*\d+[\.\)]\s*", "", a)
                parts.append(f"{i}. {_clean_protocol_refs(cleaned)}")

        # Always show danger signs
        refer = data.get("refer_if", [])
        if refer:
            parts.append("\n**Refer immediately if:** " + "; ".join(
                _clean_protocol_refs(r) for r in refer))

    else:
        # Guidance mode — full clinical response
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
