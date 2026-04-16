# MedLocal - Offline Clinical AI for Community Health Workers

**Kaggle Gemma 4 Good Hackathon 2026**
**Tracks:** Health & Sciences | Digital Equity & Inclusivity | Global Resilience
**Special Technology:** LiteRT Prize - Gemma 4 E2B running on Samsung S24 at 6.2s via LiteRT-LM (Google AI Edge's official on-device LLM runtime, built on LiteRT)
**Author:** Jayson Steffens | Apache 2.0 | [github.com/stffns/medlocal](https://github.com/stffns/medlocal)

---

## The Problem

It's 2 a.m. in a rural clinic. A mother brings in her 1-month-old with a fever. The community health worker (CHW) has no internet, no signal, no doctor within hours. Is this an emergency? What now?

**37% of the world has no reliable internet.** The CHWs who would benefit most from clinical AI work in exactly that gap - and when cloud models are available, they hallucinate drug dosages, compute controlled substance doses a CHW should never handle, and give different answers to the same question on different days.

---

## Who This Is For

**Meet Maria.** CHW in a riverside community in Amazonas, Venezuela, six hours by boat from the nearest hospital in Puerto Ayacucho. Primary language Spanish, basic Warao with indigenous patients. $180 Android phone, no data plan. Sees 20-40 patients a week: sick infants, pregnant mothers, snakebites, suspected malaria and dengue. Relies on a weathered MSF field guide and occasional HF-radio consults with a doctor in the capital.

Maria is often the only clinical presence her community sees that month. MedLocal lives on her phone, no signal required. She asks in Spanish, gets WHO-grounded actions in Spanish, and is told to **refer urgently** when the case is out of scope.

---

## What MedLocal Does

MedLocal is an offline clinical consultation tool that turns a phone or laptop into a WHO protocol reference that talks back. The CHW asks a question in their language. MedLocal finds the relevant protocol, checks for safety issues, and responds with specific actions, drug dosages, danger signs, and a traceable source citation.

**Example** (verbatim Gemma 4 E4B output). CHW: *"Puedo darle aspirina a un nino de 4 anos con fiebre?"*

> Aspirina esta contraindicada en ninos menores de 12 anos por riesgo de sindrome de Reye con enfermedad viral. Use Paracetamol 10-15 mg/kg cada 6 horas, maximo 60 mg/kg/dia (seguro en asma, tratamiento alternativo recomendado). Pese al nino para dosificar correctamente.
>
> **Confidence:** HIGH | **Source:** Drug Safety Age Pregnancy WHO.

No hallucination. Every fact traces to a published protocol.

---

## Multimodal in Action

A mother hands Maria a blister pack and asks if it's safe for her son. Maria points the camera at it:

> **Input:** photo of an amoxicillin 500 mg blister + text *"nino de 7 anos, 22 kg, dolor de garganta hace 3 dias"*
>
> Gemma 4 E4B reads the label -> identifies amoxicillin 500 mg -> retrieves the pediatric dosing protocol -> returns:
>
> **Assessment:** Posible faringitis; dosis pediatrica apropiada por peso.
> **Actions:** Amoxicilina 40 mg/kg/dia dividido c/8h -> 22 kg x 40 / 3 ~ 290 mg por toma. Una capsula de 500 mg es DEMASIADO. Usar suspension 250 mg/5 mL.
> **Refer if:** estridor, sialorrea, trismo, o sin mejoria a 48h.

One Gemma 4 checkpoint reads the drug label **and** reasons over the retrieved protocol - no OCR service, no second model, no network. Every additional model is another 2-4 GB that doesn't fit on Maria's phone.

*(Vision pipeline is functional; not yet covered by the benchmark suite.)*

---

## Why Gemma 4 - Structured Output as a Safety Contract

The single Gemma 4 feature MedLocal depends on most is **native JSON schema enforcement**.

Every consultation is schema-constrained: `{condition, assessment, actions[], dosages[], refer_if[], allergy_check, source[]}`. The safety pipeline pattern-matches `dosages[]` against source text, scans `actions[]` for controlled drugs, and blocks on `allergy_check` surgically, because schema enforcement guarantees the fields exist and conform.

Without structured output you parse prose with regex. With it, Gemma 4 becomes a function: input -> structured clinical record -> verifiable by downstream guards. That's the difference between a demo and a safety-critical tool.

**Also critical:** multimodal in a single 6.3 GB checkpoint (text + vision + reasoning + 7 languages) and Apache 2.0 licensing for frictionless NGO and ministry deployment.

---

## How It Works

MedLocal is not a chatbot. It is a **retrieval system with a safety layer**.

1. CHW asks a question in any language.
2. **Pre-flight classifier** (Gemma 4, structured call): in-scope? emergency? what clinical terms to search?
3. **Protocol retrieval** over 75+ structured WHO/MSF protocols using a 4-pass cross-lingual search.
4. Gemma 4 reads retrieved protocols and emits **schema-constrained JSON**.
5. **Post-generation safety pipeline** verifies every field against source text before the CHW sees a word.

The critical principle: **the model never invents**. It formats and selects from retrieved protocols. If the protocols don't cover the question, MedLocal refers to a clinician.

---

## The Anti-Hallucination Architecture

A medical AI that occasionally invents a drug dose is worse than no AI. Our defense has nine layers:

1. **Pre-flight scope rejection** - out-of-scope questions are refused before retrieval ever fires.
2. **Retrieval, not generation** - the model only sees protocol text, never its own training knowledge.
3. **Confidence scoring** - weak retrieval -> "refer to clinician" instead of guessing.
4. **Vague-query detection** - asks for clarification instead of assuming.
5. **Contraindication scan** - drug x patient attributes (age, pregnancy, allergies) checked against known contraindications.
6. **Controlled-drug guard** - refuses opioid, sedative, and chemotherapy dosing entirely.
7. **Dosage cross-check** - verifies every numerical value against the source protocol text.
8. **Allergy guard** - blocks the named drug and its pharmacological class siblings.
9. **Emergency fast-path** - regex detects IMCI danger signs at zero LLM cost and forces urgent referral.

When any layer fires, it **overwrites the model's answer** with a safe refusal. The model doesn't get a vote on safety - the pipeline does.

---

## What We Validated

**101/101 (100%) on a 15-category adversarial benchmark.** Three highlights:

- **Hallucination probes 6/6.** Questions deliberately crafted to elicit fabricated dosages or citations. All refused or grounded.
- **Cross-lingual emergency 5/5.** Neonatal fever phrased in Swahili, French, Hindi, Portuguese, Spanish - all detected as emergency, all referred.
- **Contraindication 4/4.** Aspirin/Reye, ibuprofen/infant, metronidazole/1st-trimester, ACE-inhibitor/pregnancy - all caught pre-prescription.

Full 15-category breakdown and reproducible test suite: `tests/benchmark_comprehensive.py` | [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Engineering Challenges We Overcame

- **Cross-lingual retrieval gap.** The multilingual embedder buried critical chunks (organophosphate/atropine) that FTS ranked #1. Fix: 4-pass retrieval - 3 hybrid passes (`vec=0.3, fts=0.7, mmr=1.0`) plus a BM25-only safety-net that rescues FTS-rank-1 chunks.
- **Markdown chunker destroying context.** The store splits at every `##` header *before* size checks, so a 4-header protocol returned only 1 chunk per query. Fix: AT MOST ONE `##` per file, enforced by `medlocal protocol validate`.
- **Silent truncation at ctx=4096.** Preflight + consult + JSON schema overflowed LM Studio's default context. Fix: require `n_ctx >= 8192`.
- **Model-layer safety is not enough.** Gemma occasionally injects LaTeX or drifts a dose. Fix: the 9-guard post-generation pipeline is authoritative.
- **Regression on every protocol addition.** New protocols shift MMR/RRF ranking and silently break unrelated cases. Fix: full benchmark is a mandatory gate on every KB change.

---

## Deployment Readiness

| | Laptop (dev) | **Samsung S24 Ultra (LiteRT-LM spike)** |
|---|---|---|
| Model | Gemma 4 E4B Q4_K_M | Gemma 4 E2B Q4 |
| RAM used | ~7 GB | ~4.4 GB |
| Consultation latency | 16-20s (p95 ~25s) | **6.2s** |
| Retrieval | SQLite + FTS5 + vectors | SQLite + FTS5 |
| Internet | none | none |

**Minimum hardware:** any Android 12+ phone with 8 GB RAM. Ingest of the 75-protocol core KB takes ~90s on the laptop, ~3 min on the phone - one-time setup.

**Already built:** 201 FSRS-6 spaced-repetition training cards for CHW onboarding - covering protocol navigation, danger sign recognition, and dosage lookup workflows.

---

## Limitations (Honest Assessment)

Not a medical device - research demonstration only. Q4 quantization produces occasional non-deterministic responses; the safety pipeline catches most but not all. 75 protocols cover common CHW scenarios but not everything. Multilingual quality is uneven (ES/FR strong, SW/HI acceptable, AM marginal). No longitudinal context. Android port is a proof-of-concept spike; the local web UI is the production path today.

---

## What's Next

Seeking an NGO or ministry-of-health partner for a supervised field pilot. Country-specific protocols (Venezuelan and Amazon-basin first), training card field validation, and the three-week Android production port on the LiteRT-LM spike.

---

## Try It

**Kaggle Notebook:** [`notebooks/medlocal_demo_executed.ipynb`](notebooks/medlocal_demo_executed.ipynb) - runs end-to-end on Kaggle's free tier, no local install required.

**Local:**

```bash
git clone https://github.com/stffns/medlocal.git && cd medlocal
pip install -e ".[dev]"
# Load Gemma 4 E4B in LM Studio (ctx=10000, temperature=0)
medlocal ingest data/core/protocols --profile core
medlocal serve # -> http://localhost:8765
```

---

> Research/educational demonstration only - not a medical device. See [LICENSE](../LICENSE).

*Technical deep-dive: [ARCHITECTURE.md](ARCHITECTURE.md) | Pipeline internals: [PIPELINE.md](PIPELINE.md) | Protocol sources: [SOURCES.md](SOURCES.md)*
