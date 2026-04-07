# MedLocal

Offline clinical consultation & training for community health workers.
Built for the **Kaggle Gemma 4 Good Hackathon 2026**.

## Project Context

- **Author:** Jayson Steffens
- **License:** Apache 2.0
- **Target LLM:** Gemma 4 E4B/E2B (on-device, multimodal)
- **Teacher LLM:** Gemini 2.5 Flash (offline, generates consultation index + training cards)
- **Target users:** Community health workers without internet access
- **Hackathon tracks:** Health, Education, Accessibility

## Architecture

### Anti-Hallucination Design
- vstash IS the knowledge — the LLM only formats/selects, never invents
- Core KB is CLOSED (read-only) — ships with validated WHO protocols
- Pre-flight translator (`preflight.py`): single structured call classifies scope
  + vital-emergency BEFORE retrieval; out-of-scope short-circuits without vstash
- Consultation index: teacher model generates Q&A pairs offline in CHW language
- Judge validates against BOTH expected answer AND source protocol (double grounding)
- Keyword expansion translates symptoms to clinical terms — does NOT diagnose
- Safety layer: emergency detection, dosage cross-check, confidence scoring, audit log

### Unified Conversational Interface
Single tab with text + camera + follow-ups:
- Text questions with multi-turn context
- Camera: visual triage, medication ID, document scan
- Structured JSON output via schema (forces condition naming)
- Follow-up questions refine diagnosis iteratively

### Dual-Profile Knowledge Base
- `core` (read-only) — 54 WHO/MSF protocols + 162 consultation index pairs
- `local` (editable) — Country-specific protocols, scanned documents
- Federated search via vstash (hybrid vector + keyword, RRF)

### Stack
- **vstash** — Retrieval engine (SQLite, local embeddings, NDCG@10=0.7255 on SciFact)
- **Gemma 4 E4B/E2B** — On-device judge, consultation, vision
- **Gemini Flash** — Teacher: generates consultation index + training cards (offline)
- **FSRS-6** — Spaced repetition scheduling (90% retention target)
- **FastAPI** — Local-only web server with mobile UI
- **Pydantic** — Structured output schema for consistent responses

## Safety Layer (safety.py)
- Emergency detection: regex patterns for danger signs (zero LLM cost, fast path)
- Confidence scoring: LOW/MEDIUM/HIGH based on retrieval quality
- Dosage cross-check: verifies dosages in answer match source protocols
- Grounding verification: optional LLM check for hallucination
- Audit log: SQLite record of every consultation

## Pre-flight Translator (preflight.py)
- Single `chat_structured()` call after the regex fast path, before retrieval
- Returns `{clinical_terms, intent, out_of_scope, rejection_reason, vital_emergency}`
- `out_of_scope=true` → static refusal, no vstash hit (fixes HP03 "what blood tests?")
- `vital_emergency=true` → forces guidance mode + referral prefix
- Owns scope classification and cross-lingual emergency reasoning ONLY; retrieval
  still uses the legacy `_KEYWORDS_PROMPT` expansion that was tuned for the corpus
- System prompt teaches reasoning-by-principle: IMCI danger signs, qualifier
  downgrades ("only", "mild", "stable"), narrow out-of-scope drug list
- 3 reference few-shots (routine in-scope, emergency in-scope, open-diagnosis
  out-of-scope) — no memorised case answers
- Requires LM Studio n_ctx ≥ 8192 (4096 causes silent truncation on complex cases)

## Key Conventions
- Default on-device endpoint: `http://localhost:1234/v1` (LM Studio)
- Config: `./medlocal.toml` or `~/.medlocal/config.toml`
- `[llm]` = on-device model (Gemma), `[teacher_llm]` = large model (Gemini)
- Protocols MUST cite WHO/MSF source with year
- Protocols must be <=2000 chars or split into focused files
- NEVER use LLM diagnosis in retrieval pipeline — only symptom translation
- ALWAYS ask drug allergies before recommending medication
- Response language MUST match question language

## Commands

```bash
medlocal ingest <source> --profile core|local   # Ingest protocols
medlocal consult "<question>"                    # One-shot clinical Q&A
medlocal chat                                    # Interactive consultation
medlocal train "<topic>"                         # Generate training cards
medlocal index                                   # Generate consultation index
medlocal study [--topic <topic>]                 # Spaced repetition session
medlocal search "<query>"                        # Direct KB search
medlocal serve [--port 8765]                     # Start web server + API
```

## API Endpoints

- `GET /` — Mobile web UI
- `POST /api/consult` — Clinical consultation (structured JSON)
- `POST /api/ingest` — Ingest documents
- `POST /api/vision/triage` — Visual triage (image upload)
- `POST /api/vision/medication` — Medication identification
- `POST /api/vision/scan` — Document scan + auto-ingest
- `POST /api/train/generate` — Generate training cards
- `GET /api/train/session` — Get study session
- `POST /api/train/answer` — Submit & evaluate answer
- `GET /api/train/topics` — List topics
- `GET /api/chunk/{id}` — View source protocol text
- `GET /api/search` — Search KB

## File Structure

```
medlocal/
  __init__.py
  config.py        # Pydantic config, LLM + teacher_llm separation
  llm.py           # chat() + chat_structured() with JSON schema
  knowledge.py     # Dual-profile vstash (core + local), federated search
  preflight.py     # Pre-flight scope + emergency classifier (structured call)
  consult.py       # Consultation pipeline with structured output + safety + preflight
  safety.py        # Emergency detection, confidence, dosage check, audit
  training.py      # FSRS scheduling, teacher/judge with double grounding
  store.py         # SQLite training cards + review history
  indexer.py       # Consultation index generator (teacher model)
  vision.py        # Visual triage, medication ID, document scan
  api.py           # FastAPI endpoints
  web.py           # Mobile-first HTML UI (single file)
  cli.py           # Typer CLI
data/core/protocols/  # 54+ structured clinical protocols (WHO/MSF sourced)
tests/
  benchmark_comprehensive.py   # 96-case suite, 13 categories — release gate (~22 min)
  smoke_critical.py            # 17 critical cases — dev loop (~3 min)
  test_e2e.py                  # 22 E2E cases (legacy)
docs/
  constitution.md   # Project vision and hackathon objective
  ARCHITECTURE.md   # System architecture, pipeline diagram, benchmarks, lessons
  ROADMAP.md        # 6-phase plan with insights
  SOURCES.md        # Source documents plan with URLs and validation checklist
```

## Development

```bash
pip install -e ".[dev]"
ruff check medlocal/
pytest tests/

# Fast dev loop — 17 critical cases, ~3 min
python tests/smoke_critical.py

# Release gate — 96 cases, 13 categories, ~22 min
python tests/benchmark_comprehensive.py
```

**LM Studio context window:** load the model with `n_ctx ≥ 8192`. Default
4096 causes silent truncation in the preflight + consult + schema stack on
complex cases, which manifests as flaky failures and higher tail latency.

## Testing with different models

```toml
# medlocal.toml — Gemma E4B (default)
[llm]
model = "gemma-4-e4b-it"
base_url = "http://localhost:1234/v1"

# Gemma E2B (smaller, faster, phone-friendly)
[llm]
model = "gemma-4-e2b-it"
base_url = "http://localhost:1234/v1"

# Gemini Flash (cloud, for comparison)
[llm]
provider = "gemini"
model = "gemini-2.5-flash"
base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
```

## Known Limitations
- Gemma 4B sometimes injects LaTeX (`\geq`) and protocol numbers despite instructions
- Multilingual quality depends on model: Flash > E4B > E2B for low-resource languages
- Diagnostic variability on ambiguous symptoms (fever+headache) — mitigated by differential protocol
- Retrieval depends on chunk size — large protocols may not surface relevant sections
- `_TRIAGE_PROMPT_BASE` in vision.py does NOT instruct text extraction, so photos
  of medication packages routed to `/api/vision/triage` describe the box visually
  instead of reading drug labels → age-safety checks don't fire. Fix pending.
- No foreign-body-aspiration protocol yet. Pediatric wheeze questions pattern-match
  to asthma even when the presentation is a clear choking episode with unilateral
  findings. Fix pending.

## Benchmarks (gemma-4-e4b-it @ 8192 ctx)
- **Comprehensive:** 96/96 (100%) — all 13 categories at 100% (2026-04-07)
- **Avg latency:** 15.42s/query, p95 24.5s, total 22 min
- **HP03 ("what blood tests should I order?"):** formerly KNOWN FAILURE, now resolved
  via preflight out-of-scope short-circuit before retrieval
