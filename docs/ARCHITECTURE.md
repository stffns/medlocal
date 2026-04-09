# MedLocal — Product Roadmap & Architecture

## Project Overview

MedLocal is an offline-first clinical consultation and training system for community health workers (CHWs). It combines vstash (hybrid retrieval engine with SOTA benchmarks), Gemma 4 (E2B and E4B, on-device multimodal LLMs released 2026-03-31), and FSRS (spaced repetition) to deliver clinical decision support, adaptive training, and visual triage — all without internet. As of the 2026-04-09 sprint, both the E2B (~2 GB RAM at Q4_K_S) and E4B (~5 GB RAM) configurations score 101/101 on the 101-case adversarial clinical benchmark with the LLM-as-judge evaluator, tied with each other and within one harness-wording-artefact case of Gemini 3.1 Pro. The pipeline, not the model size, is the determinant of clinical safety across the 2B-4B range.

**Repository:** Private — github.com/stffns/medlocal
**Hackathon:** Kaggle Gemma 4 Good — Deadline May 18, 2026
**License:** Apache 2.0

---

## Architecture Principles

1. **Offline is sacred.** Everything must work without internet. No exceptions.
2. **Connectivity is opportunistic.** When available, use it to update and enrich — never to gate functionality.
3. **Knowledge lives in documents, not in model weights.** No fine-tuning. vstash retrieves, the model reasons over context.
4. **Degrade gracefully.** Full hybrid search when embeddings are available, keyword-only when they're not.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BUILD-TIME (with internet)                  │
│                                                                     │
│  WHO PDFs ──┐                                                       │
│  MSF Guides ┼──► vstash ingest ──► core.db (SQLite + embeddings)    │
│  CHT XForms ┘    (chunk_size=2048, paraphrase-multilingual)         │
│                                                                     │
│  Result: Single .db file with all chunks + pre-computed vectors     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ distribute once
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         RUNTIME (no internet, always)               │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐              │
│  │  core.db    │  │  local.db    │  │ training.db   │              │
│  │ (read-only) │  │ (editable)   │  │ (FSRS state)  │              │
│  │ WHO + CHT   │  │ local docs + │  │ 201 cards +   │              │
│  │ 95 docs     │  │ field notes  │  │ 15 topics     │              │
│  └──────┬──────┘  └──────┬───────┘  └───────────────┘              │
│         │                │                                          │
│         └───── federated search (vstash RRF) ─────┘                │
│                          ▲                                          │
│                          │                                          │
│            ┌─────────────┴──────────────┐                          │
│            │    Pre-flight translator    │                          │
│            │  (preflight.py, single LLM) │                          │
│            │  scope verdict + emergency  │                          │
│            │  short-circuit OR continue  │                          │
│            └─────────────┬──────────────┘                          │
│                          │                                          │
│              ┌───────────┴───────────┐                              │
│              │    Gemma 4 E2B / E4B  │                              │
│              │  (LM Studio / Ollama  │                              │
│              │   / llama.cpp)        │                              │
│              │  text + image         │                              │
│              │  n_ctx = 12 000       │                              │
│              └───────────────────────┘                              │
│                          │                                          │
│              ┌───────────┴───────────┐                              │
│              │  Unified Interface    │                              │
│              │ Consult + Vision +    │                              │
│              │ Follow-up + Train +   │                              │
│              │ Search + Admin        │                              │
│              └───────────────────────┘                              │
└─────────────────────────────────────────────────────────────────────┘
```

### Consult pipeline (post-preflight)

```
question
   │
   ▼
_extract_search_query()   strip triage brackets
   │
   ▼
detect_emergency()        regex fast-path, zero LLM cost
   │ (hit?)─────────────────► emergency guidance mode
   │ no
   ▼
preflight()               single structured LLM call
   │ out_of_scope? ───────────► static refusal (no retrieval)
   │ vital_emergency? ────────► set emergency flag
   ▼
_multi_query_search()     4-pass vstash retrieval:
   │                       1. raw question (hybrid, FTS-boosted)
   │                       2. _KEYWORDS_PROMPT English expansion (hybrid)
   │                       3. preflight.clinical_terms (hybrid, when available)
   │                       4. FTS-ONLY safety-net on the expansion (BM25 alone)
   │                       Merged by chunk_id, max score wins, top 20, then
   │                       filtered to relevant[:6] for LLM context.
   │                       See docs/PIPELINE.md §3 for the full story.
   ▼
score_confidence()        LOW → refer, HIGH/MED → continue
   │
   ▼
chat_structured()         schema-enforced clinical response
   │
   ▼
check_dosages()           cross-reference answer vs source protocols
   │
   ▼
audit.log()               SQLite record
```

---

## Current Implementation Status

### IMPLEMENTED (working, tested)

| Component | File | Description |
|-----------|------|-------------|
| Config | `medlocal/config.py` | Pydantic config, LLM + teacher_llm separation |
| LLM client | `medlocal/llm.py` | `chat()` + `chat_structured()` with JSON schema |
| Knowledge base | `medlocal/knowledge.py` | Dual-profile vstash, chunk_size=2048, federated search |
| Pre-flight translator | `medlocal/preflight.py` | Single structured call: scope verdict + vital-emergency flag + clinical search terms. Runs before retrieval; out-of-scope short-circuits without touching vstash |
| Consultation | `medlocal/consult.py` | Structured output, multi-query retrieval, guided assessment mode, preflight wiring |
| Safety | `medlocal/safety.py` | Emergency detection, confidence scoring, dosage check, audit log |
| Training | `medlocal/training.py` | FSRS scheduling, teacher/judge with double grounding |
| Training store | `medlocal/store.py` | SQLite cards + review history |
| Vision | `medlocal/vision.py` | Triage, medication ID, document scan + CHW text context |
| CHT converter | `tools/cht_converter.py` | XForm XML → structured markdown, default + Malawi apps |
| Web UI | `medlocal/web.py` | Unified conversational UI, mobile-first, camera integration |
| API | `medlocal/api.py` | FastAPI REST endpoints for all features |
| CLI | `medlocal/cli.py` | Typer CLI with all commands |
| Indexer | `medlocal/indexer.py` | Consultation index generator (tested, removed from pipeline — caused contamination) |

### PLANNED (not yet implemented)

| Component | Description | Priority |
|-----------|-------------|----------|
| Sync manager | Opportunistic sync when connectivity available | P2 |
| Embedding bridge | Stateless service for deferred embeddings | P2 |
| Guided Triage Engine | Dedicated module for decision tree traversal (currently in prompt) | P1 |
| PWA manifest | Install to homescreen, offline service worker | P2 |
| Android native | LiteRT-LM integration for native Gemma inference | P3 |

---

## Dual-Profile Knowledge Base

### core.db (read-only, distributed with app)
- **73 WHO / MSF / UNICEF / AAP protocols** — structured markdown with dosages,
  steps, danger signs. Authoring rule: ≤1 `##` per file, prefer bold labels,
  so each protocol fits in one vstash chunk. Validated by
  `medlocal protocol audit`. Long sources are split into focused sub-files
  (e.g. `poisoning-organophosphate-who.md` + `poisoning-general-who.md`).
- **28 CHT workflows** — decision trees from PIH Malawi + default reference app
- **Total:** 101 documents, all single-chunk
- **Format:** SQLite + vec_chunks (384d, paraphrase-multilingual-mpnet-base-v2)
  + fts_chunks (FTS5 Porter stemming)
- **Chunk size:** protocols are flat single-chunk files; CHT workflows use the
  vstash default (2048 tokens, 256 overlap)
- **Retrieval:** hybrid RRF with `vec_weight=0.3, fts_weight=0.7, mmr_lambda=1.0`
  via `_store.search` directly (Memory.search does not forward these knobs).
  A 4th BM25-only pass in `_multi_query_search` rescues FTS-rank-1 chunks
  the multilingual embedder buries. See `docs/PIPELINE.md` §3.3.

### local.db (editable by supervisor/admin)
- Country-specific protocols, regional guidelines
- Scanned documents (via vision mode document scan)
- Admin manages via web UI

---

## Guided Assessment Mode (IMPLEMENTED)

When clinical information is insufficient, the system asks ONE question at a time instead of guessing.

### How it works (current implementation via prompt + schema)

```
CHW: "nino con tos y fiebre"

MedLocal (assessment mode):
  Evaluating: Respiratory infection / fever differential
  "So far I know: child with cough and fever, but I need more to classify."

  Next question:
  "How old is the child? (Breathing rate thresholds differ by age:
   <2mo: >=60/min, 2-11mo: >=50/min, 12mo-5yr: >=40/min)"

  While assessing:
  1. Check for danger signs immediately
  2. Keep child hydrated

  Refer immediately if: unable to drink, convulsions, lethargic, stiff neck

CHW: "3 years old, breathing 48 times per minute"

MedLocal (guidance mode):
  Assessment: Pneumonia — fast breathing (48 > 40 threshold for age 3)
  Actions:
  1. Amoxicillin 750mg twice daily for 5 days
  2. Follow up in 3 days
  Refer if: chest indrawing, not improving in 3 days
  Source: Pneumonia IMCI
```

### Schema
The structured output has a `mode` field:
- `"assessment"` — needs more info, includes `next_question`
- `"guidance"` — enough info, includes full `actions` + `refer_if`

---

## Model Safety Benchmarks

### 101-Case Comprehensive Benchmark — 2026-04-09 final (LLM-judge verified)

```
Overall: 101/101 (100%) on both E2B and E4B with the MedLocal pipeline.

safety               12/12 (100%)    hallucination     6/6  (100%)
emergency             8/8  (100%)    protocol         14/14 (100%)
clinical             20/20 (100%)    contraindication  4/4  (100%)
dosage                8/8  (100%)    multilingual      5/5  (100%)
emergency_skip        7/7  (100%)    rabies            4/4  (100%)
age_safety            3/3  (100%)    anaphylaxis       3/3  (100%)
cross_lingual_emerg   5/5  (100%)    heavy_metals      1/1  (100%)
child_protection     1/1  (100%)
```

**Final configuration comparison (LLM-judge verified):**

| Config | Score | Avg latency | Params (effective) | Target device | Tested on | Offline |
|---|---|---|---|---|---|---|
| **A — E4B + MedLocal** | **101/101 (100 %)** | 29 s | 4 B | Laptop / tablet | laptop (llama.cpp Q4_K_S, ctx=12000) | ✅ |
| **B — E2B + MedLocal** | **101/101 (100 %)** | **19 s** | **2 B** | **phone-class memory profile** | laptop (llama.cpp Q4_K_S, ctx=12000) | ✅ |
| **C — Gemini 3.1 Pro naive** | 100/101 (99 %) | 17 s | not disclosed | Cloud only | Google API | ❌ |

The Gemini 3.1 Pro residual (HP03) is a harness wording artefact
confirmed by the LLM-as-judge audit, not a clinical error — see
hackathon writeup §5.4 for the explicit retraction of the earlier
draft's overclaims and §5.6 for the case-by-case audit.

**Evolution on the growing suite:**

| Date       | Cases | Context | E4B Score           | E2B Score           | Notes                       |
|------------|-------|---------|---------------------|---------------------|-----------------------------|
| Pre-preflight | 96 | 4096    | 93/96 (96.9%)       | not tested          | HP03 known failure          |
| 2026-04-05 | 96    | 4096    | 92-94/96 flaky      | not tested          | Silent ctx truncation       |
| 2026-04-06 | 96    | 8192    | 96/96 (100%)        | not tested          | First clean full run        |
| 2026-04-07 | 99    | 8192    | **99/99 expected**  | not tested          | Post-revert [:8]→[:6]       |
| 2026-04-08 | 101   | 8192    | 97/101 (regex-only) | 99/101 (regex-only) | Silt review: 4 silent-failure fixes landed, suite grew to 101 |
| 2026-04-09 | 101   | **12000**| **101/101 (judge)** | **101/101 (judge)** | **LLM-judge + Capa I allergy guardrail + malaria boundary fix**. Final hackathon state. |

The 2026-04-08 session (four silent-failure fixes from the Silt
review) and the 2026-04-09 session (LLM-judge, allergy guardrail,
malaria weight-band fix, five new protocols) closed the gap between
regex-only and judge-verified scoring on both on-device
configurations. The hackathon writeup §6 has the full narrative of
both sessions.

**Context-window finding:** raising `n_ctx` to 12 000 from the
2026-04-08 setting of 8192 eliminates silent truncation on the
longest preflight + consult + schema stacks. 12 000 is the minimum
ctx we run in production; the runtime check in
`medlocal/runtime_check.py` fails loud if the LM Studio endpoint
reports a smaller loaded context.

### Fast smoke suite (`tests/smoke_critical.py`)

20 hand-picked cases, 1-2 per category, ~5 min. Use this for dev
iteration; only run the full comprehensive benchmark as a release gate.

### Legacy benchmarks (pre-2026-04-08, retained for reference only)

Earlier versions of this document had a 24-scenario benchmark and
an 8-model allergy safety table with "E2B ❌" and "Gemini Pro ⚠"
entries. Both tables were correct for their time but are now
superseded by the 101-case LLM-judge benchmark above. The
superseded claims are retracted in the hackathon writeup §5.4:
the LLM-as-judge audit showed that the alleged Gemini Pro allergy
failure was a harness wording artefact, and the PRIORITY 0
allergy guardrail (Capa I, commit `33f5edb`) closed the E2B
allergy gap so E2B now ties E4B at 101/101.

---

## vstash Retrieval Benchmarks

### vs Published Baselines (BEIR)

| Dataset | Docs | NDCG@10 | vs BM25 | vs ColBERTv2 |
|---------|------|---------|---------|--------------|
| SciFact | 5K | 0.7255 | +9.1% | +4.7% |
| SciDocs | 25K | 0.1911 | +21.0% | +24.1% |
| NFCorpus | 3.6K | 0.3525 | +8.5% | +2.5% |
| FiQA | 57K | 0.3789 | +60.6% | +6.4% |

### vs Chroma (same embedding model)

| Dataset | vstash | Chroma | Delta |
|---------|--------|--------|-------|
| SciFact | 0.7255 | 0.7201 | +0.7% |
| NFCorpus | 0.3525 | 0.3379 | +4.3% |

---

## CHT Integration

### Implemented
- CHT XForm converter (`tools/cht_converter.py`)
- Default reference app: 7 forms (pregnancy, delivery, postnatal)
- PIH Malawi app: 21 forms (IMCI under-5, over-5, TB, HIV, immunization, family planning)
- Total: 28 CHT workflows converted and ingested

### Available for future integration (14 reference apps)
- Maternal & Newborn Health, Contact Tracing, Event Based Surveillance
- Pharmacovigilance, Stock Monitoring, Learning & Care
- Country-specific apps (Kenya, Uganda, Nepal)

---

## Lessons Learned

| Lesson | Detail |
|--------|--------|
| Consultation index worsened quality | Q&A pairs caused false positive matches. Removed. Raw protocols + clean retrieval wins. |
| ≤1 H2 per file is load-bearing (retraction of the earlier chunk_size row) | Earlier versions of this table said `chunk_size=2048` resolved the retrieval gaps. That was a partial truth — the deeper rule is that vstash's chunker splits at every markdown header BEFORE checking size, so a 1500-char file with five `##` sections produces five independently-ranked fragments. 64 of 67 protocols had to be flattened to bold-labels structure during the 2026-04-08 session. The authoring rule is "≤1 `##` per file, prefer bold labels, one chunk per protocol". Validated by `medlocal protocol audit`. |
| Keyword expansion must NOT diagnose | Only translate symptoms to clinical terms. Diagnostic expansion = hidden hallucination. |
| E2B is viable with the right pipeline (retraction) | Earlier versions of this table said "E2B is not viable for generative mode, fails drug allergy safety". That observation was correct for E2B with a naive prompt but is no longer true: with the PRIORITY 0 allergy guardrail (Capa I, commit `33f5edb`), E2B scores 101/101 on the 101-case judged benchmark. The pipeline is the determinant of clinical safety across the 2B-4B range. The E2B vs E4B trade-off is about response richness, not viability. See the hackathon writeup §5.5. |
| "Bigger model != safer" retraction | Earlier versions said "Gemini Pro failed the allergy test" as evidence. The LLM-as-judge audit in the 2026-04-09 session found that the alleged failure was a harness wording artefact. Gemini 3.1 Pro scores 100/101 on the same suite with a naive prompt (the single residual HP03 is also a wording artefact). The honest version of the lesson is: "a cloud frontier model and a 2B on-device model can produce clinically equivalent answers on the same suite if both are evaluated under a non-brittle harness — what differentiates them is deployment properties, not clinical capability on this corpus". |
| Specific safety rules create bias | Hardcoded rules ("don't diagnose measles from fever alone") biased other queries. Generic rules work better. |
| Continuous testing after every protocol change | Adding a protocol shifts the MMR/RRF ranking for every other case. DA05 (malaria dose for a 12 kg child) silently regressed from PASS to FAIL after the pneumonia safety-floor landed — cross-protocol weight-band content confused the small model's band-boundary reasoning. Fix: every KB edit requires a full bench re-run, not spot-checking the target case. See commit `d07a90f` and the feedback_continuous_testing memory. |
| User-reported constraints need a PRIORITY 0 guard, not a prompt hope | Allergies live in the user's question, not in any retrieved protocol. The small model sometimes propagated the constraint and sometimes did not — non-deterministic at temperature 0.0. Fix: extract before the LLM call, inject a hard prompt constraint, post-process the answer and override if the model slipped. Same defense-in-depth pattern as the controlled-drug guard. |
| The protocol must be explicit enough that a small model cannot misread it | DA05 was not a retrieval failure — the right chunk was at rank 1. It was a reading failure at the boundary between two weight bands. Fix: rewrite the protocol with worked examples naming the specific boundary values ("a 12 kg child receives 1 tablet"), not "fix the model". |
| LLM-as-judge closes the whack-a-mole regex failure mode | The 2026-04-08 whack-a-mole row was a partial fix (widened lookback + unit tests for wordings that had broken the regex). The real fix is the two-layer evaluator in `tests/judge.py`: regex fast path for the 90 % a regex can decide, Gemini 2.5 Flash judge for the ambiguous 10 %. Verdicts cached in `tests/.judge_cache.json` for byte-deterministic reruns. The judge cleared six Gemini regex artefacts in the 2026-04-09 run. |
| Be honest about the residuals, including the ones that look good | The earlier draft of the hackathon writeup claimed Gemini 3.1 Pro failed several cases that turned out to be harness artefacts. Retracting those claims was uncomfortable and the right thing to do. A medical app cannot afford a writeup that over-promises, even in its own favour. |
| Vision needs CHW context | Image alone insufficient. Combined image + text context produces correct diagnoses. |
| "Not covered" must orient, not abandon | Generic "not covered" is unhelpful. Explain WHY outside scope + who to consult. |
| Scope classification must be explicit, not implicit | Relying on retrieval similarity scores to detect "out of CHW scope" is brittle. A dedicated pre-flight classifier (one structured call) with reasoning-by-principle is more robust and short-circuits before paying for retrieval. |
| Reference examples > memorised answers | Early preflight used 8-9 hardcoded few-shots and regressed on unseen cases. 3 examples that teach the REASONING pattern (qualifier downgrades, IMCI danger signs, diagnostic planning vs protocol execution) generalise better. |
| Preflight owns scope/emergency only, not retrieval keywords | Passing preflight's clinical terms to vstash caused dose-lookup regressions. Keeping the legacy `_KEYWORDS_PROMPT` expansion for retrieval preserves baseline quality. Preflight does the classification work the regex cannot. |
| Context overflow masquerades as model variability | A cluster of "flaky" failures (ST03, PA06, CC04, CA15, ES04) were all symptoms of silent truncation when preflight + consult + schema overflowed 4096 tokens. Raising ctx to 8192 fixed them all and also reduced latency. Check context before chasing "flaky" tests. |
| `_check_absent` must strip markdown | The benchmark's negation lookback failed on `**do not**` because the markdown asterisks broke the `"do not "` substring match. Strip `* _ ~` before the lookback so "**DO NOT** give water" is correctly recognised as negated guidance, not a prescription. |
| Danger signs include envenomation with progression | IMCI lists neuro/resp/circ/dehydration/toxicology — but a snake/scorpion bite with spreading swelling or ascending red streaks also qualifies. Added as an explicit preflight category. |
| Multilingual embedder is the weakest link for cross-lingual clinical retrieval | `paraphrase-multilingual` did not bridge "fumigando papas + miosis + sudando" to the organophosphate protocol — the chunk fell outside the top-87 vector candidates. BM25 found it at rank 1/83. Fix: FTS-boosted weights (0.3/0.7) + a dedicated 4th `fts_only=True` pass. See `docs/PIPELINE.md` §3.3. |
| MMR dedup at default 0.5 silently drops single-chunk documents | vstash's `_mmr_dedup` eliminated a single-chunk protocol, blaming "another chunk from the same document" that did not exist. Fix: always pass `mmr_lambda=1.0` for clinical-protocol corpora where every file is already a focused concept. |
| `Memory.search()` does not forward `vec_weight`/`fts_weight`/`mmr_lambda` | Medlocal now calls `_store.search` directly with a manually-computed `embed_query`. Documented as `TODO(vstash-upstream)` in `knowledge.py`. |
| Safety flag dedup via helper, not scattered guards | Four code paths can flag the same consult as an emergency. Scattering `if flag not in safety_flags` guards is fragile — a new path can regress. Centralised in a local `_flag()` helper so the invariant lives in one place. |
| Split protocols at authoring time, not at retrieval time | A 2557-char `poisoning-who.md` split at `## Immediate Actions` and the atropine block ended up in the non-matching chunk. Fix was to split the file into focused sub-files, each ≤2000 chars → 1 chunk. The ≤2000 char authoring rule is load-bearing, not stylistic. |

---

## File Structure (actual)

```
medlocal/
├── pyproject.toml
├── README.md
├── medlocal.toml                 # Runtime config (gitignored — has API keys)
├── medlocal/
│   ├── __init__.py
│   ├── config.py                 # Pydantic config, LLM + teacher_llm
│   ├── llm.py                    # chat() + chat_structured() with JSON schema
│   ├── knowledge.py              # Dual-profile vstash (core + local)
│   ├── preflight.py              # Pre-flight scope + emergency classifier (structured LLM)
│   ├── consult.py                # Consultation + guided assessment mode + preflight wiring
│   ├── safety.py                 # Emergency detection, confidence, dosage, audit
│   ├── training.py               # FSRS + teacher/judge double grounding
│   ├── store.py                  # SQLite training cards + review history
│   ├── indexer.py                # Consultation index generator (deprecated)
│   ├── vision.py                 # Triage, medication ID, scan + text context
│   ├── api.py                    # FastAPI endpoints
│   ├── web.py                    # Mobile-first HTML UI (single file)
│   └── cli.py                    # Typer CLI
├── data/core/
│   ├── protocols/                # 73 WHO/MSF/UNICEF/AAP structured protocols, single-chunk
│   ├── cht-workflows/            # 28 CHT decision trees (default + Malawi)
│   ├── who/                      # Downloaded WHO PDFs (not committed)
│   ├── msf/                      # Downloaded MSF PDFs (not committed)
│   └── hesperian/                # Downloaded Hesperian PDFs (not committed)
├── tools/
│   └── cht_converter.py          # XForm XML → markdown converter
├── tests/
│   ├── __init__.py
│   ├── test_unit.py                   # 79 unit tests (JSON repair, negation, allergy, runtime, structured-LLM-parse)
│   ├── test_e2e.py                    # 22 E2E test cases (legacy)
│   ├── benchmark_models.py            # 24-scenario model comparison (legacy)
│   ├── benchmark_comprehensive.py     # 101-case suite — 15 categories, release gate (~30 min on E2B)
│   ├── benchmark_baseline.py          # Cloud baseline (Gemini 3.1 Pro naive prompt + judge)
│   ├── judge.py                       # LLM-as-judge fallback (regex fast path + Gemini Flash judge)
│   ├── .judge_cache.json              # Cached judge verdicts for byte-deterministic reruns
│   └── smoke_critical.py              # 20-case critical-path suite (~5 min)
├── notebooks/
│   ├── _build_demo_notebook.py        # Generator script for the Kaggle Tier A demo
│   └── medlocal_demo.ipynb            # Kaggle Tier A demo notebook (7 cases)
├── CHANGELOG.md                   # Version history (keep-a-changelog format)
└── docs/
    ├── constitution.md            # Project vision and hackathon objective
    ├── ARCHITECTURE.md            # This file — system overview + benchmarks + lessons
    ├── PIPELINE.md                # Deep dive on consult flow + retrieval internals
    ├── ROADMAP.md                 # Phase plan with next steps
    └── SOURCES.md                 # Source documents with URLs and validation
```

---

## Hackathon Submission Checklist

- [x] Working web demo with clinical scenarios
- [x] **101-case adversarial benchmark with LLM-judge evaluator** — E4B 101/101, E2B 101/101, Gemini 3.1 Pro 100/101 (HP03 wording artefact)
- [x] vstash BEIR benchmarks (5 datasets + Chroma head-to-head)
- [x] Vision mode demo (progressive disclosure)
- [x] Constitution document
- [x] **73 WHO/MSF/UNICEF/AAP protocols** + 28 CHT workflows, all single-chunk validated
- [x] **9-layer anti-hallucination pipeline** with Capa I PRIORITY 0 allergy guardrail
- [x] Guided assessment mode (decision tree follow-up)
- [x] **79 unit tests** (`tests/test_unit.py`)
- [x] **Hackathon writeup honest rewrite** with §5.4 Gemini overclaim retraction, §5.6 manual residual audit, §5.7 scope-and-limits
- [x] **AI-assistance disclosure** with protagonist framing in README, writeup, and notebook Acknowledgments
- [x] **Kaggle Tier A demo notebook** (`notebooks/medlocal_demo.ipynb`) — 7 representative cases, switched to Gemma 4 (`gemma-4-26b-a4b-it`) as the cloud-demo consult LLM
- [x] Open source repository (Apache 2.0)
- [ ] Pre-built core.db for distribution (P1, blocks the Android APK)
- [ ] **Android-native APK running Gemma 4 E2B on a real phone** (the headline next step — see the hackathon writeup §9 item 1 and ROADMAP.md "The one that matters most")
