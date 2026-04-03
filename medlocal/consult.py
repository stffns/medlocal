"""Consultation mode — clinical Q&A backed by protocol retrieval."""

from __future__ import annotations

from .config import LLMConfig
from .knowledge import KnowledgeBase
from .llm import chat

_SYSTEM_PROMPT = """\
You are a clinical decision support assistant for community health workers.

IMPORTANT RULES:
1. ONLY use the retrieved protocols below to answer. Never invent medical advice.
2. Structure your response as:
   - **Assessment:** What the symptoms/situation suggest
   - **Recommended Actions:** Step-by-step protocol from the guidelines
   - **Warning Signs:** When to refer to a higher-level facility
   - **Source:** Which guideline/protocol this comes from
3. If the retrieved context does not cover the question, say so clearly.
4. Use simple, clear language appropriate for community health workers.
5. Respond in the same language as the question."""


def consult(
    question: str,
    kb: KnowledgeBase,
    llm_cfg: LLMConfig,
    *,
    history: list[dict[str, str]] | None = None,
) -> tuple[str, list[dict]]:
    """Answer a clinical question using retrieved protocols.

    Returns:
        Tuple of (answer_text, sources).
    """
    results = kb.search(question, top_k=5)

    if not results:
        return (
            "No relevant clinical protocols found in the knowledge base. "
            "Please consult a supervisor or refer the patient.",
            [],
        )

    context = ""
    sources = []
    for i, r in enumerate(results, 1):
        context += f"[{i}] {r.title} (profile: {r.profile})\n{r.text}\n\n"
        sources.append({
            "title": r.title,
            "score": round(r.score, 3),
            "profile": r.profile,
        })

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({
        "role": "user",
        "content": f"## Retrieved Protocols\n\n{context}\n## Question\n\n{question}",
    })

    answer = chat(messages, llm_cfg)
    return answer, sources
