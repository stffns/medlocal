# MedLocal

Offline clinical consultation & training for community health workers.
Built for the **Kaggle Gemma 4 Good Hackathon 2026**.

## Project Context

- **Author:** Jayson Steffens
- **License:** Apache 2.0
- **Target LLM:** Gemma 4 E4B (on-device, multimodal, 4B effective params)
- **Target users:** Community health workers without internet access
- **Hackathon tracks:** Health, Education, Accessibility

## Architecture

### Five Operational Modes
1. **Consultation** — RAG clinical Q&A with protocol retrieval
2. **Chat** — Multi-turn interactive conversation
3. **Training** — FSRS-6 spaced repetition with LLM-generated cards (3 levels: concept, recall, scenario)
4. **Vision** — Visual triage, medication ID, document scanning (Gemma 4 multimodal)
5. **Admin** — Local protocol management

### Dual-Profile Knowledge Base
- `core` (read-only) — WHO guidelines, essential medicines. Ships with app.
- `local` (editable) — Country-specific protocols, scanned documents.
- Federated search via vstash (hybrid vector + keyword, RRF).

### Stack
- **vstash** — Retrieval engine (SQLite, local embeddings)
- **Gemma 4 E4B** — Generation, evaluation, vision (via OpenAI-compatible API)
- **FSRS-6** — Spaced repetition scheduling (90% retention target)
- **FastAPI** — Local-only web server for mobile UI
- **SQLite** — All storage in portable single files
- **Typer + Rich** — CLI interface

## Key Conventions

- Default LLM endpoint: `http://localhost:1234/v1` (LM Studio / Ollama)
- Config file: `~/.medlocal/config.toml` or `./medlocal.toml`
- All responses must cite source protocols — never invent medical advice
- Support bilingual interaction (respond in user's language)
- Training cards grounded in protocol text only

## Commands

```bash
medlocal ingest <source> --profile core|local   # Ingest protocols
medlocal consult "<question>"                    # One-shot clinical Q&A
medlocal chat                                    # Interactive consultation
medlocal train "<topic>"                         # Generate training cards
medlocal study [--topic <topic>]                 # Spaced repetition session
medlocal search "<query>"                        # Direct KB search
medlocal serve [--port 8765]                     # Start API server
```

## API Endpoints

- `POST /api/consult` — Clinical consultation
- `POST /api/ingest` — Ingest documents
- `POST /api/train/generate` — Generate training cards
- `GET /api/train/session` — Get study session
- `POST /api/train/answer` — Submit & evaluate answer
- `GET /api/train/topics` — List topics
- `GET /api/search` — Search KB

## Development

```bash
pip install -e ".[dev]"
ruff check medlocal/
pytest
```

## TODO (Hackathon)

- [ ] Vision mode (image analysis via Gemma 4 multimodal)
- [ ] Mobile-first web UI
- [ ] Pre-built core KB with WHO guidelines
- [ ] Kaggle notebook demo
- [ ] Retrieval benchmarks
