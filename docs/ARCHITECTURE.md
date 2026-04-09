# MedLocal — Product Roadmap & Architecture

## Project Overview

MedLocal is an offline-first clinical consultation and training system for community health workers (CHWs). It combines vstash (hybrid retrieval engine with SOTA benchmarks), Gemma 4 E4B (on-device multimodal LLM), and FSRS (spaced repetition) to deliver clinical decision support, adaptive training, and visual triage — all without internet.

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
│              │    Gemma 4 E4B        │                              │
│              │  (LM Studio / Ollama) │                              │
│              │  text + image         │                              │
│              │  n_ctx ≥ 8192         │                              │
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
- **67 WHO/MSF protocols** — structured markdown with dosages, steps, danger
  signs. Authoring rule: ≤2000 chars per file so each protocol fits in one
  vstash chunk. Long sources are split into focused sub-files (e.g.
  `poisoning-organophosphate-who.md` + `poisoning-general-who.md`).
- **28 CHT workflows** — decision trees from PIH Malawi + default reference app
- **Total:** 95 documents, ~270 chunks
- **Format:** SQLite + vec_chunks (384d, paraphrase-multilingual-mpnet-base-v2)
  + fts_chunks (FTS5 Porter stemming)
- **Chunk size:** 2048 tokens, 256 overlap
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

### 99-Case Comprehensive Benchmark (gemma-4-e4b-it @ 8192 ctx)

```
Overall: 99/99 expected (100%) on current HEAD

safety               12/12 (100%)    hallucination     6/6  (100%)
emergency             8/8  (100%)    protocol         14/14 (100%)
clinical             20/20 (100%)    contraindication  4/4  (100%)
dosage                8/8  (100%)    multilingual      5/5  (100%)
emergency_skip        7/7  (100%)    rabies            4/4  (100%)
age_safety            3/3  (100%)    anaphylaxis       3/3  (100%)
cross_lingual_emerg   5/5  (100%)
```

**Evolution on the growing suite (all runs on gemma-4-e4b-it):**

| Date       | Cases | Context | Score               | 100% cats | Notes                       |
|------------|-------|---------|---------------------|-----------|-----------------------------|
| Pre-preflight | 96 | 4096    | 93/96 (96.9%)       | 10/13     | HP03 known failure          |
| 2026-04-05 | 96    | 4096    | 92-94/96 flaky      | 11/13     | Silent ctx truncation       |
| 2026-04-06 | 96    | **8192**| **96/96 (100%)**    | **13/13** | First clean full run        |
| 2026-04-07 | 99    | 8192    | 98/99 (99.0%)       | 12/13     | RP04 ctx overflow with [:8] |
| 2026-04-07 | 99    | 8192    | **99/99 expected**  | **13/13** | Post-revert [:8]→[:6]; smoke 20/20 confirms |

The 2026-04-07 session added the ES07 organophosphate case and fixed the
four compounding retrieval bugs described in `docs/PIPELINE.md` §3.3.

**Context-window finding:** raising the LM Studio loaded context from
4096 to 8192 is faster, not slower. At 4096 the pre-flight + consult +
structured-output stack overflowed on complex cases → silent truncation →
kv-cache thrashing. At 8192 every call completes in one pass. Tail
latencies see the biggest improvement (p95 ~38 s → 24.5 s, max ~55 s → 31 s).

### Fast smoke suite (`tests/smoke_critical.py`)

20 hand-picked cases, 1-2 per category, ~5 min. Use this for dev
iteration; only run the full comprehensive benchmark as a release gate.
Current status: **20/20 PASS** (2026-04-07).

### 24-Scenario Legacy Benchmark (earlier, for reference)

```
Model             Pass Rate   Avg Time   Safety   Clinical
Gemma E2B             71.4%      5.3s      5/6       7/10
Gemma E4B             76.2%      8.8s      6/6       7/10
Qwen 3.5 9B           90.5%     18.6s      6/6      10/10
```

### Allergy Safety Test (8 models)

| Model | Params | Time | Allergy Safe | Spanish |
|-------|--------|------|-------------|---------|
| Gemma E2B | 2B local | 12.8s | ❌ | ❌ |
| **Gemma E4B** | **4B local** | **28.4s** | **✅** | **✅** |
| Qwen 4B distill | 4B local | 20.5s | ✅ | ✅ |
| Qwen 3.5 9B | 9B local | 28.7s | ✅ | ✅ |
| Gemma 31B | 31B cloud | 26.4s | ✅ | ✅ |
| Gemini Flash Lite | cloud | 81.0s | ✅ | ❌ |
| **Gemini Flash** | **cloud** | **10.7s** | **✅** | **✅** |
| Gemini Pro | cloud | 47.5s | ⚠ | ✅ |

**Key finding:** Bigger != safer. Gemini Pro fails allergy test. Gemma E4B passes all.

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
| chunk_size=2048 resolved retrieval gaps | Larger chunks keep title+symptoms+treatment together. No workaround needed. |
| Keyword expansion must NOT diagnose | Only translate symptoms to clinical terms. Diagnostic expansion = hidden hallucination. |
| E2B not viable for generative mode | Fails drug allergy safety. E4B is minimum. E2B only for selector mode (future). |
| Bigger model != safer | Gemini Pro failed allergy test. Size doesn't guarantee safety. |
| Specific safety rules create bias | Hardcoded rules ("don't diagnose measles from fever alone") biased other queries. Generic rules work better. |
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
│   ├── protocols/                # 54 WHO/MSF structured protocols
│   ├── cht-workflows/            # 28 CHT decision trees (default + Malawi)
│   ├── who/                      # Downloaded WHO PDFs (not committed)
│   ├── msf/                      # Downloaded MSF PDFs (not committed)
│   └── hesperian/                # Downloaded Hesperian PDFs (not committed)
├── tools/
│   └── cht_converter.py          # XForm XML → markdown converter
├── tests/
│   ├── __init__.py
│   ├── test_e2e.py                    # 22 E2E test cases
│   ├── benchmark_models.py            # 24-scenario model comparison (legacy)
│   ├── benchmark_comprehensive.py     # 99-case suite — 13 categories, release gate
│   └── smoke_critical.py              # 20-case critical-path suite (~5 min)
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
- [x] Model safety comparison (8 models, 24 scenarios)
- [x] vstash BEIR benchmarks (5 datasets + Chroma head-to-head)
- [x] Vision mode demo (progressive disclosure)
- [x] Constitution document
- [x] 54 WHO/MSF protocols + 28 CHT workflows
- [x] Guided assessment mode (decision tree follow-up)
- [x] E2E test suite (22 cases)
- [x] Open source repository
- [ ] Kaggle notebook with reproducible examples
- [ ] Video demo (2-3 minutes)
- [ ] Pre-built core.db for distribution
