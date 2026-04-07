"""Pre-flight translator — single structured LLM call that classifies a consult
question before retrieval.

Returns:
- clinical_terms: English clinical search terms (translation only)
- intent: nature of the question (protocol execution vs open diagnosis)
- out_of_scope: True if the question requires a licensed medical professional
- rejection_reason: short explanation when out of scope
- vital_emergency: True if life-threatening danger signs are present

The CHW scope boundary is reasoning-based, not keyword-based:
  IN SCOPE  — applying a known protocol/test to specific symptoms
              ("fever in malaria-endemic area, do RDT?", "child has diarrhea, ORS dose?")
  OUT OF SCOPE — open-ended diagnostic planning or prescriptive choices that
              require a license ("what tests should I order?", "which antibiotic?",
              "what's wrong with this patient?")

This sits ahead of the legacy `_KEYWORDS_PROMPT` retrieval keyword expansion and
unifies what was previously a separate emergency regex pass. The regex
`detect_emergency()` in safety.py is kept as a zero-cost fast path before this
function is called.
"""

from __future__ import annotations

import logging

from .config import LLMConfig
from .llm import chat_structured

logger = logging.getLogger(__name__)


_PREFLIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "clinical_terms": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "English clinical search terms extracted from the question. "
                "TRANSLATION ONLY — never a diagnosis. Example: "
                "'niño con fiebre y sarpullido' -> ['pediatric', 'fever', 'rash', 'exanthem']."
            ),
        },
        "intent": {
            "type": "string",
            "enum": [
                "protocol_execution",
                "open_diagnosis",
                "specific_treatment",
                "general_information",
                "out_of_domain",
            ],
            "description": (
                "protocol_execution = applying a known protocol/test to symptoms. "
                "open_diagnosis = open-ended 'what's wrong / what tests / what to order'. "
                "specific_treatment = asking for a specific drug/dose for a stated condition. "
                "general_information = general health education. "
                "out_of_domain = unrelated to clinical care."
            ),
        },
        "out_of_scope": {
            "type": "boolean",
            "description": (
                "True if the question requires a licensed medical professional. "
                "Set TRUE for: open diagnostic planning, ordering/interpreting labs or imaging, "
                "selecting antibiotic class without a protocol, prescribing controlled drugs, "
                "surgical or invasive procedures. "
                "Set FALSE if the CHW just needs to apply a documented protocol or POC test."
            ),
        },
        "rejection_reason": {
            "type": "string",
            "description": (
                "Short reason (one sentence) when out_of_scope is true. "
                "Empty string when in scope."
            ),
        },
        "vital_emergency": {
            "type": "boolean",
            "description": (
                "True if the question describes life-threatening danger signs: "
                "convulsions, not breathing, severe bleeding, shock, eclampsia, "
                "unconsciousness, severe dehydration, anaphylaxis."
            ),
        },
    },
    "required": [
        "clinical_terms",
        "intent",
        "out_of_scope",
        "rejection_reason",
        "vital_emergency",
    ],
}


_PREFLIGHT_SYSTEM = """\
You classify a clinical question for a community health worker (CHW) assistant.
You do NOT diagnose. You only return four pieces of metadata about the question.

# 1. clinical_terms
Return 4-8 English clinical search terms that describe what the question is about:
the patient (age, sex, pregnancy), the main symptoms or signs, the body system,
and any relevant context (endemic area, exposure, comorbidity).

This field is STRICT TRANSLATION + INDEXING ONLY — it is NOT a differential
diagnosis. Hard rules:

  - You MAY translate a lay symptom into its clinical synonym
    (e.g. "orinando mucho" → "polyuria", "ve borroso" → "blurred vision",
    "le duele el pecho" → "chest pain"). This is just renaming the symptom.

  - You MUST NOT add disease names, syndromes, families, or differential
    diagnoses that the user did not state. Do NOT add "diabetes",
    "preeclampsia", "gestational hypertension", "pneumonia", "malaria",
    "stroke", "anaphylaxis", or any other -itis / -emia / -osis label
    unless the user literally used that word. The retrieval layer will
    find the right protocol; your job is to surface the SYMPTOMS, not
    to guess the diagnosis.

  - When in doubt about whether a term is translation or diagnosis,
    drop it. A leaner term list with only the patient + raw symptoms
    is always safer than one biased by a wrong differential.

# 2. intent
Choose the option that best describes what the user is asking the assistant to do.

# 3. out_of_scope  (default: false — be permissive)
A community health worker is trained on a broad set of documented protocols.
The default answer is out_of_scope = FALSE. Only mark TRUE in the narrow
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

Mark out_of_scope = TRUE only when one of these specific conditions is met:

  1. The user asks the CHW to DESIGN a laboratory workup from scratch — i.e.
     pick which tests to order without reference to a protocol
     ("which blood tests should I order?", "what labs do I run?", "what workup?")

  2. The user asks the CHW to INTERPRET imaging or culture results
     ("read this X-ray", "what does the ultrasound show?", "interpret this CT")

  3. The user asks specifically about a drug from this short specialist list:
       chemotherapy agents, second-line ARVs, vancomycin, propofol, ketamine
       (for sedation), midazolam (for sedation), opioids by injection,
       general anaesthetics, immunosuppressants
     For ANY OTHER drug — including antibiotic alternatives for allergies,
     drug-drug interactions of common OTC medicines, pre-referral injectable
     antibiotics (e.g. ceftriaxone, gentamicin, ampicillin), antimalarials,
     antiepileptics for status, and dose lookups for ANY drug a CHW might
     give — leave out_of_scope = FALSE. The downstream assistant has
     the protocols and will check whether a documented answer exists.

  4. The user asks the CHW to PERFORM an invasive specialist procedure
     (lumbar puncture, intubation, surgery, central line, chest tube,
     endotracheal suctioning, pleural tap)

Anything not in those four buckets is IN SCOPE. In particular, the following
are IN SCOPE and must NOT be rejected:
  - Drug-allergy alternatives ("child allergic to penicillin, what antibiotic?")
  - Drug-drug interactions for OTC or first-line drugs
    ("can I give ibuprofen with daily aspirin?")
  - Pre-referral antibiotic doses ("ceftriaxone dose for meningitis pre-referral")
  - Suspecting and managing common syndromes from a presentation
    ("sustained fever >7 days, stepwise rising temperature, headache")
  - Any question whose answer might plausibly live in a CHW protocol —
    let the downstream retrieval decide.

When in doubt, leave out_of_scope = FALSE. The assistant has its own
"out of scope of available protocols" fallback for retrieval misses; your job
is only to catch the obviously-unanswerable questions before retrieval.

# 4. vital_emergency  (default: false)
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
  - Toxicology: ANY pediatric ingestion of household chemicals, cleaning products,
    pesticides, kerosene, caustics, button batteries, or medications — regardless
    of the parent-reported amount ("a little", "un poco", "a sip"). Severity of
    caustic or chemical exposure cannot be assessed remotely; treat as emergency.
    Adult intentional overdose or large accidental overdose is also vital_emergency.
  - Envenomation and bites with PROGRESSION: snake, scorpion, or spider bite with
    swelling that is spreading, ascending, or accompanied by systemic signs
    (bleeding, weakness, numbness, altered consciousness); any bite or wound with
    red streaks spreading from it (ascending lymphangitis); severe burn covering
    a large area or involving face/airway/hands/genitals. A local-only reaction
    ("bee sting, only localized swelling") is NOT this — the key word is
    PROGRESSION or SYSTEMIC involvement.
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

When in doubt about vital_emergency, prefer FALSE — the downstream assistant has
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
A: {"clinical_terms": ["pediatric", "diarrhea", "stable", "drinking",
       "hydration", "ORS"],
    "intent": "protocol_execution",
    "out_of_scope": false,
    "rejection_reason": "",
    "vital_emergency": false}

# Example B — explicit IMCI danger sign, in scope, IS an emergency.
# Reasoning: chest indrawing is an IMCI severe-pneumonia danger sign regardless of
# what language it is written in. The classifier reasons about the SIGN, not the words.
Q: "Bebé respira muy rápido y se le hunden las costillas al respirar"
A: {"clinical_terms": ["infant", "fast breathing", "chest indrawing",
       "respiratory distress", "severe pneumonia"],
    "intent": "protocol_execution",
    "out_of_scope": false,
    "rejection_reason": "",
    "vital_emergency": true}

# Example C — open diagnostic planning, requires clinician judgement, OUT of scope.
# Reasoning: the user is asking the CHW to design a workup; no protocol can decide
# which lab panels to order from a blank slate.
Q: "What blood tests should I order for this patient?"
A: {"clinical_terms": ["laboratory workup", "diagnostic planning"],
    "intent": "open_diagnosis",
    "out_of_scope": true,
    "rejection_reason": "Designing a laboratory panel requires clinician-level judgement;
       CHWs run only protocol-defined point-of-care tests.",
    "vital_emergency": false}
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

    if not isinstance(result, dict) or "intent" not in result:
        return {}

    # Defensive defaults
    result.setdefault("clinical_terms", [])
    result.setdefault("out_of_scope", False)
    result.setdefault("rejection_reason", "")
    result.setdefault("vital_emergency", False)
    return result
