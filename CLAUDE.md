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
- `core` (read-only) — 67 WHO/MSF protocols (structured markdown, ≤2000 chars each)
- `local` (editable) — Country-specific protocols, scanned documents
- Federated search via vstash with FTS-boosted hybrid retrieval:
  - 3 hybrid passes (raw, English expansion, preflight terms) with
    `vec_weight=0.3, fts_weight=0.7, mmr_lambda=1.0`
  - 4th BM25-only safety-net pass that rescues FTS-rank-1 chunks the
    multilingual embedder buries (see `docs/PIPELINE.md` §3.3)

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
- **Protocol authoring rule (load-bearing, 2026-04-08):** use AT MOST ONE
  `##` header per file. Prefer `**bold labels**` for sub-sections.
  vstash's chunker splits at EVERY markdown header before checking size,
  so a file with four `##` produces four chunks and the LLM only sees
  one of them per query. The `poisoning-organophosphate-who.md` file is
  the template. Run `medlocal protocol validate <path>` before committing
  any protocol change, and `medlocal protocol audit` before releases.
- When content is genuinely too large for one flat file, split into
  focused sibling files (e.g. `measles-who.md` alone, not
  `measles-diagnosis-who.md` + `measles-treatment-who.md` — unless the
  sub-topics are independent enough that only one is ever relevant to a
  given query).
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
data/core/protocols/  # 67 structured clinical protocols (WHO/MSF sourced, ≤2000 chars each)
tests/
  benchmark_comprehensive.py   # 99-case suite, 13 categories — release gate (~25 min)
  smoke_critical.py            # 20 critical cases — dev loop (~5 min)
  test_e2e.py                  # 22 E2E cases (legacy)
docs/
  constitution.md   # Project vision and hackathon objective
  ARCHITECTURE.md   # System architecture, pipeline diagram, benchmarks, lessons
  PIPELINE.md       # Deep dive on consult flow, retrieval internals, debug playbook
  ROADMAP.md        # Phase plan with insights
  SOURCES.md        # Source documents plan with URLs and validation checklist
CHANGELOG.md        # Version history (keep-a-changelog format)
```

## Development

```bash
pip install -e ".[dev]"
ruff check medlocal/
pytest tests/

# Fast dev loop — 20 critical cases, ~5 min
python tests/smoke_critical.py

# Release gate — 99 cases, 13 categories, ~25 min
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
- **Comprehensive:** 99/99 expected (100%) on current HEAD — all 13 categories at 100%
  (last full run 2026-04-07 was 98/99 with a temporary `relevant[:8]` cap that
  overflowed RP04; reverted to `[:6]`, smoke 20/20 confirms the fix)
- **Avg latency:** ~16-20s/query, p95 ~25s
- **HP03 ("what blood tests should I order?"):** resolved via preflight
  out-of-scope short-circuit before retrieval (2026-04-07)
- **ES07 (organophosphate cholinergic toxidrome):** added 2026-04-07 as the
  smoking gun that exposed the FTS/vector retrieval bug; now passes with
  atropine + soap-and-water decontamination correctly surfaced

## Retrieval notes (2026-04-07 session)
- See `docs/PIPELINE.md` §3 for the deep dive on the 4-pass retrieval and
  the FTS-only safety-net that rescues chunks the multilingual embedder buries
- `KnowledgeBase.search` bypasses `Memory.search()` and calls
  `_store.search` directly to forward `vec_weight/fts_weight/mmr_lambda`.
  The `TODO(vstash-upstream)` block in `knowledge.py` lists the 4 vstash
  improvements that would let us delete this workaround
