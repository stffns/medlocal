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
│  │ 82 protocols│  │ field notes  │  │ 15 topics     │              │
│  └──────┬──────┘  └──────┬───────┘  └───────────────┘              │
│         │                │                                          │
│         └───── federated search (vstash RRF) ─────┘                │
│                          │                                          │
│              ┌───────────────────────┐                              │
│              │    Gemma 4 E4B        │                              │
│              │  (LM Studio / Ollama) │                              │
│              │  text + image         │                              │
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

---

## Current Implementation Status

### IMPLEMENTED (working, tested)

| Component | File | Description |
|-----------|------|-------------|
| Config | `medlocal/config.py` | Pydantic config, LLM + teacher_llm separation |
| LLM client | `medlocal/llm.py` | `chat()` + `chat_structured()` with JSON schema |
| Knowledge base | `medlocal/knowledge.py` | Dual-profile vstash, chunk_size=2048, federated search |
| Consultation | `medlocal/consult.py` | Structured output, multi-query retrieval, guided assessment mode |
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
- **54 WHO/MSF protocols** — structured markdown with dosages, steps, danger signs
- **28 CHT workflows** — decision trees from PIH Malawi + default reference app
- **Total:** 82 documents, 204KB, ~246 chunks
- **Format:** SQLite + vec_chunks (384d) + fts_chunks (FTS5 Porter stemming)
- **Chunk size:** 2048 tokens, 256 overlap (vstash 0.17.1)
- **Size:** ~3MB

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

### 24-Scenario Benchmark (chunk_size=2048, no consultation index)

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

---

## File Structure (actual)

```
medlocal/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── medlocal.toml                 # Runtime config (gitignored — has API keys)
├── medlocal/
│   ├── __init__.py
│   ├── config.py                 # Pydantic config, LLM + teacher_llm
│   ├── llm.py                    # chat() + chat_structured() with JSON schema
│   ├── knowledge.py              # Dual-profile vstash (core + local)
│   ├── consult.py                # Consultation + guided assessment mode
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
│   ├── test_e2e.py               # 22 E2E test cases
│   └── benchmark_models.py       # 24-scenario model comparison
└── docs/
    ├── constitution.md            # Project vision and hackathon objective
    ├── ARCHITECTURE.md            # This file
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
