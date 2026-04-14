# MedLocal - Offline Clinical AI for Community Health Workers

**Kaggle Gemma 4 Good Hackathon 2026**
**Impact tracks:** Health & Sciences · Global Resilience · Digital Equity & Inclusivity
**Author:** Jayson Steffens · Apache 2.0 · [github.com/stffns/medlocal](https://github.com/stffns/medlocal)

---

## The Problem

It's 2 a.m. in a rural clinic in Sub-Saharan Africa. A mother brings in her 1-month-old baby with a fever. The community health worker has no internet, no phone signal, no doctor within two hours. She needs to know: is this an emergency? What should I do right now?

**37% of the world has no reliable internet.** The community health workers (CHWs) who would benefit most from clinical AI live and work in exactly that gap. Cloud-only medical assistants are useless where they are most needed.

And when cloud models are available, they fail in the ways that matter most to clinical safety: they hallucinate drug dosages, they compute controlled substance doses a CHW should never handle, they fabricate citations, and they give different answers to the same question depending on the day.

---

## What MedLocal Does

MedLocal is an offline clinical consultation tool that turns a phone or laptop into a WHO protocol reference that talks back. The CHW asks a question in their language. MedLocal finds the relevant protocol, checks for safety issues, and responds with specific actions, drug dosages, danger signs, and a traceable source citation.

**A real example.** A CHW types: *"Puedo darle aspirina a un niño de 4 años con fiebre?"*

MedLocal responds:
> **Condition:** Fiebre
> **Assessment:** Aspirina está contraindicada en niños menores de 12 años por riesgo de síndrome de Reye.
> **Actions:**
> 1. No dar aspirina a este niño.
> 2. Administrar Paracetamol 10-15 mg/kg cada 6 horas.
> 3. Pesar al niño para calcular la dosis exacta.
> **Source:** WHO/UNICEF IMCI Guidelines; Drug Safety Age Pregnancy WHO.

No hallucination. No improvisation. Every fact traces to a published protocol.

---

## Why Gemma 4

MedLocal uses **Gemma 4 E4B** (4 billion parameters, Q4_K_M quantization, ~6.3 GB) running entirely on-device through LM Studio or LiteRT-LM on Android. The same model handles:

- **Text consultations** in 7+ languages (Spanish, French, Swahili, Portuguese, Hindi, Arabic, English)
- **Visual triage** - photo of a wound, medication package, or printed document
- **Clinical reasoning** - contraindication detection, emergency classification, triage screening

One model, one download, zero cloud dependency. The multimodal capability means a CHW can photograph a medication package and ask "is this safe for my pregnant patient?" without switching tools.

We also validated with **Gemma 4 E2B** (2 billion parameters, ~4.4 GB) - the phone-friendly configuration that runs on a Samsung Galaxy S24 with 6.2 second consultation latency.

---

## How It Works (Without the Jargon)

MedLocal is not a chatbot. It is a **retrieval system with a safety layer**.

1. **The CHW asks a question** in any language
2. **Pre-flight check** - a fast classifier determines: is this in scope? Is it an emergency? What clinical terms should we search for?
3. **Protocol retrieval** - searches a local database of 75+ structured WHO/MSF protocols using a 4-pass search strategy that works across languages
4. **The model reads the protocols and responds** with structured output: condition, assessment, specific actions with dosages, referral criteria, and source citation
5. **Post-generation safety checks** - verifies dosages match the source protocol, catches controlled drug doses, checks for allergy violations

The critical design principle: **the model never invents**. It formats and selects from retrieved protocols. If the protocols don't cover a question, MedLocal says so and refers to a clinician. This is what makes it safe enough for a CHW to use alone.

---

## What We Validated

**99/101 (98%) on a comprehensive adversarial benchmark** covering 15 clinical safety categories:

| Category | Result | What it tests |
|---|---|---|
| Safety traps | 11/12 | Controlled drugs, scope violations, dangerous combinations |
| Emergency detection | 8/8 | IMCI danger signs, poisoning, anaphylaxis, neonatal fever |
| Clinical accuracy | 19/20 | Correct condition identification and treatment |
| Dosage accuracy | 8/8 | Specific drug doses match WHO protocols |
| Hallucination probes | 6/6 | Questions designed to elicit fabricated information |
| Contraindication | 4/4 | Aspirin/Reye, ibuprofen/infant, pregnancy drugs |
| Multilingual | 5/5 | Same clinical quality in ES, FR, SW, PT, HI |
| Cross-lingual emergency | 5/5 | Emergency detection regardless of input language |
| Child protection | 1/1 | Non-accidental injury pattern recognition |
| Rabies / Anaphylaxis | 7/7 | WHO Category III bites, epinephrine dosing |

The two residual failures are non-deterministic edge cases in the Q4 quantized model, not systematic gaps.

**Qualitative findings from manual testing:**
- Correctly refuses aspirin for a 4-year-old (Reye syndrome) and recommends paracetamol with dose
- Detects neonatal fever (< 2 months) as emergency and refers immediately
- Recognizes "itching on palms during pregnancy" as cholestasis, not normal discomfort
- Identifies right lower quadrant pain + fever + vomiting as possible appendicitis, not typhoid
- Recognizes bilateral symmetrical burns in a child as abuse pattern
- Asks for trimester before prescribing metronidazole in pregnancy
- Refuses to answer when the question doesn't specify a condition (asks instead of guessing)

---

## Protocols - The Knowledge Base

MedLocal ships with **75+ structured clinical protocols** covering:

- **Pediatrics:** fever assessment (IMCI), pneumonia, diarrhea/dehydration, malnutrition, measles, varicella
- **Maternal health:** pre-eclampsia, cholestasis, medication safety in pregnancy, family planning
- **Emergencies:** anaphylaxis, poisoning (general + organophosphate + heavy metals), snakebite, burns, drowning/CPR, choking
- **Infectious disease:** malaria, dengue, tuberculosis, HIV/PEP, STIs, meningitis, typhoid, cholera
- **Safety:** drug contraindications by age/pregnancy, controlled drug refusal, drug allergy alternatives
- **Child protection:** maltreatment recognition, non-accidental burn patterns, sexual abuse red flags
- **Chronic disease:** diabetes, hypertension, asthma, epilepsy, depression

Every protocol cites its WHO/MSF source with verifiable URLs. Protocols are plain markdown files that a clinician can edit with a text editor - no retraining, no re-deployment, just edit and re-ingest.

---

## The Anti-Hallucination Architecture

This is the core of MedLocal. A medical AI that occasionally invents a drug dose is worse than no AI at all. Our defense has multiple layers:

1. **Pre-flight scope check** - out-of-scope questions (lab test ordering, imaging interpretation, surgical procedures) are rejected before retrieval
2. **Retrieval, not generation** - the model only sees protocol text, never generates from general knowledge
3. **Confidence scoring** - if retrieval quality is low, MedLocal returns "refer to a clinician" instead of guessing
4. **Vague query detection** - if the CHW doesn't state a condition or symptoms, MedLocal asks instead of assuming
5. **Contraindication scan** - drug + patient characteristics are checked against protocols before anything else
6. **Controlled drug guard** - refuses to compute doses for opioids, sedatives, chemotherapy, etc.
7. **Dosage cross-check** - every dosage in the answer is verified against the source protocol text
8. **Allergy guard** - if the CHW reports an allergy, the system blocks that drug and all class siblings
9. **Emergency fast-path** - regex patterns detect IMCI danger signs, poisoning, neonatal fever at zero LLM cost

When a layer catches a violation, it **overwrites the model's answer** with a safe refusal. The model doesn't get a vote on safety - the pipeline does.

---

## What Gemma 4 Made Possible

This project would not exist without the Gemma 4 release on March 31, 2026. Specifically:

- **E2B/E4B size** - 2-4B parameters is the sweet spot for phone deployment with clinical-quality instruction following
- **Multimodal in one checkpoint** - visual triage without a second model or network call
- **Multilingual capability** - CHWs work in Spanish, French, Swahili, Portuguese, Hindi, not just English
- **Structured output** - JSON schema enforcement produces consistent, parseable responses
- **Apache 2.0 license** - deployable in health ministries, NGOs, and government programs without legal friction

---

## Limitations (Honest Assessment)

- **Not a medical device.** MedLocal is a research demonstration, not an approved clinical tool
- **Model variability.** Q4 quantization on a 4B model means occasional non-deterministic responses. The safety pipeline catches most issues, but not all
- **Protocol coverage.** 75 protocols cover the most common CHW scenarios but not everything. Rare conditions may return "refer to a clinician"
- **Language quality.** Multilingual capability degrades for low-resource languages - French and Spanish are strong, Swahili and Hindi are acceptable, Amharic is marginal
- **No longitudinal context.** Each consultation is independent - no patient records, no follow-up tracking
- **Android port is proof-of-concept.** The web UI on a local server is production-quality; the native Android app works but with lower response quality due to on-device inference constraints

---

## What's Next

1. **Field pilot** - partner with an NGO operating CHW programs to test with real users in a supervised setting
2. **Protocol expansion** - add country-specific formularies and facility-level guidelines
3. **Spaced repetition training** - 201 training cards with FSRS-6 scheduling are built but need field validation
4. **Android native** - the LiteRT-LM port runs Gemma 4 E2B on a Samsung S24 in 6.2 seconds. Three-week port to production quality is planned

---

## Try It

```bash
git clone https://github.com/stffns/medlocal.git
cd medlocal
pip install -e ".[dev]"

# Load Gemma 4 E4B in LM Studio (ctx=10000, temperature=0)
medlocal ingest data/core/protocols --profile core
medlocal serve
# Open http://localhost:8765
```

---

> **Medical disclaimer.** MedLocal is a research and educational demonstration. It is not a medical device, not regulatory-approved, and not intended for clinical decision-making without supervision by a qualified healthcare professional. See [LICENSE](../LICENSE) for the full disclaimer.

---

*Technical deep-dive: [ARCHITECTURE.md](ARCHITECTURE.md) · Pipeline internals: [PIPELINE.md](PIPELINE.md) · Protocol sources: [SOURCES.md](SOURCES.md)*
