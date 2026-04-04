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
- Emergency detection: regex patterns for danger signs (zero LLM cost)
- Confidence scoring: LOW/MEDIUM/HIGH based on retrieval quality
- Dosage cross-check: verifies dosages in answer match source protocols
- Grounding verification: optional LLM check for hallucination
- Audit log: SQLite record of every consultation

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
  consult.py       # Consultation pipeline with structured output + safety
  safety.py        # Emergency detection, confidence, dosage check, audit
  training.py      # FSRS scheduling, teacher/judge with double grounding
  store.py         # SQLite training cards + review history
  indexer.py       # Consultation index generator (teacher model)
  vision.py        # Visual triage, medication ID, document scan
  api.py           # FastAPI endpoints
  web.py           # Mobile-first HTML UI (single file)
  cli.py           # Typer CLI
data/core/protocols/  # 54 structured clinical protocols (WHO/MSF sourced)
docs/
  constitution.md   # Project vision and hackathon objective
  ROADMAP.md        # 6-phase plan with insights
  SOURCES.md        # Source documents plan with URLs and validation checklist
```

## Development

```bash
pip install -e ".[dev]"
ruff check medlocal/
pytest tests/
```

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
