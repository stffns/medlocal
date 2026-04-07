"""Pre-flight translator — single structured LLM call that classifies a consult
question before retrieval.

Returns:
- terminos_clinicos_limpios: English clinical search terms (translation only)
- intencion: nature of the question (protocol execution vs open diagnosis)
- fuera_de_scope_chw: True if the question requires a medical professional
- motivo_rechazo: short explanation when out of scope
- emergencia_vital: True if life-threatening danger signs are present

The CHW scope boundary is reasoning-based, not keyword-based:
  IN SCOPE  — applying a known protocol/test to specific symptoms
              ("fever in malaria-endemic area, do RDT?", "child has diarrhea, ORS dose?")
  OUT OF SCOPE — open-ended diagnostic planning or prescriptive choices that
              require a license ("what tests should I order?", "which antibiotic?",
              "what's wrong with this patient?")

This replaces the older `_KEYWORDS_PROMPT` plain-text translation and unifies it
with emergency classification. The regex `detect_emergency()` in safety.py is
kept as a zero-cost fast path before this function is called.
"""

from __future__ import annotations

import logging

from .config import LLMConfig
from .llm import chat_structured

logger = logging.getLogger(__name__)


_PREFLIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "terminos_clinicos_limpios": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "English clinical search terms extracted from the question. "
                "TRANSLATION ONLY — never a diagnosis. Example: "
                "'niño con fiebre y sarpullido' -> ['pediatric', 'fever', 'rash', 'exanthem']."
            ),
        },
        "intencion": {
            "type": "string",
            "enum": [
                "ejecucion_protocolo",
                "diagnostico_abierto",
                "tratamiento_especifico",
                "informacion_general",
                "fuera_dominio",
            ],
            "description": (
                "ejecucion_protocolo = applying a known protocol/test to symptoms. "
                "diagnostico_abierto = open-ended 'what's wrong / what tests / what to order'. "
                "tratamiento_especifico = asking for a specific drug/dose for a stated condition. "
                "informacion_general = general health education. "
                "fuera_dominio = unrelated to clinical care."
            ),
        },
        "fuera_de_scope_chw": {
            "type": "boolean",
            "description": (
                "True if the question requires a licensed medical professional. "
                "Set TRUE for: open diagnostic planning, ordering/interpreting labs or imaging, "
                "selecting antibiotic class without a protocol, prescribing controlled drugs, "
                "surgical or invasive procedures. "
                "Set FALSE if the CHW just needs to apply a documented protocol or POC test."
            ),
        },
        "motivo_rechazo": {
            "type": "string",
            "description": (
                "Short reason (one sentence) when fuera_de_scope_chw is true. "
                "Empty string when in scope."
            ),
        },
        "emergencia_vital": {
            "type": "boolean",
            "description": (
                "True if the question describes life-threatening danger signs: "
                "convulsions, not breathing, severe bleeding, shock, eclampsia, "
                "unconsciousness, severe dehydration, anaphylaxis."
            ),
        },
    },
    "required": [
        "terminos_clinicos_limpios",
        "intencion",
        "fuera_de_scope_chw",
        "motivo_rechazo",
        "emergencia_vital",
    ],
}


_PREFLIGHT_SYSTEM = """\
You classify a clinical question for a community health worker (CHW) assistant.
You do NOT diagnose. You only return four pieces of metadata about the question.

# 1. terminos_clinicos_limpios
Return 4-8 English clinical search terms that describe what the question is about:
the patient (age, sex, pregnancy), the main symptoms or signs, the body system,
and any relevant context (endemic area, exposure, comorbidity). This is TRANSLATION
and indexing — never add a disease the user did not mention.

# 2. intencion
Choose the option that best describes what the user is asking the assistant to do.

# 3. fuera_de_scope_chw  (default: false — be permissive)
A community health worker is trained on a broad set of documented protocols.
The default answer is fuera_de_scope_chw = FALSE. Only mark TRUE in the narrow
cases at the bottom of this section.

The CHW's job covers, among many things:
  - Recognising danger signs and applying recognition tools (e.g. FAST for stroke,
    IMCI danger signs, danger signs in pregnancy, choking response)
  - First aid for any injury, sting, bite, burn, fracture, wound, drowning, snakebite
  - Animal bite first aid AND post-exposure prophylaxis decisions (rabies PEP is a
    public-health protocol the CHW follows; it is NOT veterinary medicine)
  - Symptom-driven protocol-defined treatment (ORS, zinc, paracetamol, amoxicillin,
    artemether-lumefantrine, magnesium sulfate, epinephrine IM, etc.)
  - Vaccination schedules and PEP regimens
  - Referral criteria and "when should I refer" questions
  - Maternal & newborn care steps
  - Drug doses for medications listed in CHW protocols
  - General health education and recognition questions ("what is X?", "how do I
    recognise Y?", "what are the steps for Z?") when X/Y/Z are CHW-relevant

A "what is X?" educational question is IN SCOPE if X is something a CHW must
recognise or perform — even if it sounds technical. The assistant downstream will
either find a matching protocol or refer; do not pre-reject the question.

Mark fuera_de_scope_chw = TRUE only in these narrow cases:
  1. Asking the CHW to design a laboratory panel from scratch
     ("which blood tests?", "what workup?")
  2. Asking the CHW to interpret imaging or culture results
     ("read this X-ray", "what does the CT show?")
  3. Asking the CHW to choose a drug regimen for a condition outside protocols,
     OR to adjust a specialist regimen (chemotherapy, second-line ARVs, controlled
     analgesia, sedation drugs like propofol/ketamine for procedures)
  4. Asking the CHW to perform an invasive specialist procedure
     (lumbar puncture, intubation, surgery, central line, chest tube)

If the question does not clearly fall into one of those four categories, leave
fuera_de_scope_chw = FALSE and let the downstream assistant handle it.

# 4. emergencia_vital  (default: false)
Mark TRUE only when the question explicitly describes signs that meet IMCI / IMNCI
general danger signs or other clearly life-threatening features. Use clinical
reasoning, not keyword matching:

  - Neurological: active convulsions/seizures, unconsciousness, lethargy with
    inability to drink/breastfeed, status epilepticus
  - Respiratory: not breathing, gasping, central cyanosis, severe respiratory
    distress with chest indrawing or grunting, unable to speak/feed from breathing
  - Circulation: shock signs (cold, mottled, weak pulse), severe ongoing bleeding,
    postpartum haemorrhage soaking pads
  - Obstetric: eclampsia / seizures in pregnancy, severe pre-eclampsia features,
    obstructed labour, ruptured uterus
  - Allergic: anaphylaxis with airway, breathing or systemic involvement
  - Dehydration: severe dehydration with sunken eyes AND unable to drink
  - Toxicology: child poisoning, large overdose
  - Mental health: active suicide intent or self-harm

Critical reasoning rule — READ THE QUALIFIERS in the question:
  - Words like "only", "just", "stable", "mild", "without", "no [danger sign]"
    DOWNGRADE the urgency. A "bee sting with ONLY localised swelling and NO
    breathing problem" is NOT anaphylaxis — it is a local reaction.
  - Words like "severe", "cannot", "unable to", "very", "rapid", explicit signs
    like "chest indrawing", "sunken eyes", "unconscious", "soaking", "convulsing"
    UPGRADE the urgency.
  - When the question describes a specific danger sign in the patient (regardless
    of language — "respira rápido y se le hunden las costillas", "ana degedege",
    "convulsiones", "no puede tomar"), apply the same reasoning as if it were in
    English. The classifier must be language-agnostic.

When in doubt about emergencia_vital, prefer FALSE — the downstream assistant has
its own danger-sign logic and a separate emergency regex catches the obvious cases.
Your job is the borderline reasoning the regex cannot do.

Return JSON only.
"""


_FEW_SHOT_EXAMPLES = """\
Three reference examples — they teach the REASONING shape, not memorised answers.
Apply the same reasoning to any new question regardless of language or wording.

# Example A — typical CHW symptom presentation, in scope, NOT an emergency.
# Reasoning: the qualifier "estable y bebe líquidos" downgrades urgency to routine.
Q: "Niño de 2 años con diarrea desde ayer, está estable y bebe líquidos"
A: {"terminos_clinicos_limpios": ["pediatric", "diarrhea", "stable", "drinking",
       "hydration", "ORS"],
    "intencion": "ejecucion_protocolo",
    "fuera_de_scope_chw": false,
    "motivo_rechazo": "",
    "emergencia_vital": false}

# Example B — explicit IMCI danger sign, in scope, IS an emergency.
# Reasoning: chest indrawing is an IMCI severe-pneumonia danger sign regardless of
# what language it is written in. The classifier reasons about the SIGN, not the words.
Q: "Bebé respira muy rápido y se le hunden las costillas al respirar"
A: {"terminos_clinicos_limpios": ["infant", "fast breathing", "chest indrawing",
       "respiratory distress", "severe pneumonia"],
    "intencion": "ejecucion_protocolo",
    "fuera_de_scope_chw": false,
    "motivo_rechazo": "",
    "emergencia_vital": true}

# Example C — open diagnostic planning, requires clinician judgement, OUT of scope.
# Reasoning: the user is asking the CHW to design a workup; no protocol can decide
# which lab panels to order from a blank slate.
Q: "What blood tests should I order for this patient?"
A: {"terminos_clinicos_limpios": ["laboratory workup", "diagnostic planning"],
    "intencion": "diagnostico_abierto",
    "fuera_de_scope_chw": true,
    "motivo_rechazo": "Designing a laboratory panel requires clinician-level judgement;
       CHWs run only protocol-defined point-of-care tests.",
    "emergencia_vital": false}
"""


def preflight(question: str, llm_cfg: LLMConfig) -> dict:
    """Classify a consult question before retrieval.

    Returns a dict matching `_PREFLIGHT_SCHEMA`. On any failure returns an empty
    dict so callers can fall back to the legacy path.
    """
    messages = [
        {"role": "system", "content": _PREFLIGHT_SYSTEM + "\n\n" + _FEW_SHOT_EXAMPLES},
        {"role": "user", "content": f"Q: {question.strip()}\nA:"},
    ]
    try:
        result = chat_structured(messages, llm_cfg, _PREFLIGHT_SCHEMA, "preflight")
    except Exception as exc:
        logger.warning("Preflight call failed: %s", exc)
        return {}

    if not isinstance(result, dict) or "intencion" not in result:
        return {}

    # Defensive defaults
    result.setdefault("terminos_clinicos_limpios", [])
    result.setdefault("fuera_de_scope_chw", False)
    result.setdefault("motivo_rechazo", "")
    result.setdefault("emergencia_vital", False)
    return result
