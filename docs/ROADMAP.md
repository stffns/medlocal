# MedLocal — Roadmap

## Key Insights from Genesis Conversation

### Architecture Decisions
1. **vstash IS the knowledge** — Gemma no necesita "saber" medicina. El conocimiento vive en vstash, el modelo solo razona sobre contexto recuperado.
2. **Teacher offline, Judge on-device** — Modelo grande genera Q&A pairs una vez. Gemma solo evalua respuestas contra respuestas conocidas.
3. **Core cerrado + Local abierto** — Seguridad medica. Core WHO no se toca. Local para protocolos nacionales/regionales.
4. **Web local, no app nativa** — FastAPI + HTML sirve a cualquier dispositivo con navegador.
5. **Domain-agnostic** — La arquitectura sirve para cualquier vertical. Medico es el primero.

### Lessons Learned (Session 2026-04-04)
1. **Consultation index WORSENED quality** — Q&A pairs caused false positive matches (measles from fever alone). Removed. Raw protocols + clean retrieval + capable model is the winning formula.
2. **chunk_size=2048 resolved retrieval gaps** — vstash 0.17.1 with larger chunks keeps title+symptoms+treatment together. No need for index workaround.
3. **Keyword expansion must NOT diagnose** — Only translate symptoms to clinical terms. Diagnostic expansion is hidden hallucination in the retrieval pipeline.
4. **E2B not viable for generative mode** — Fails drug allergy safety, diagnoses measles from fever alone. E4B is minimum for generation. E2B only for selector mode (future).
5. **Bigger model != safer** — Gemini Pro failed allergy test. Gemini Flash was safest cloud model.
6. **Structured JSON output via schema** — Forces model to name condition, list actions. Eliminates vague assessments.
7. **Protocol refs in output** — Small models inject "Protocol ID 1" despite instructions. Fixed with _clean_protocol_refs() post-processing.
8. **Vision needs CHW context** — Image alone insufficient for diagnosis. CHW text combined with visual findings produces correct results.

---

## Current State (2026-04-04)

### Completed
- [x] 54 clinical protocols (WHO/MSF sourced, structured markdown)
- [x] Safety layer (emergency detection, confidence, dosage check, allergy verification, audit log)
- [x] Structured JSON output via schema (forces condition naming)
- [x] Multi-query retrieval (symptom-only keyword expansion)
- [x] Judge with double grounding (Q&A pair + source protocol)
- [x] Teacher/Judge LLM separation in config
- [x] Unified web UI (consult + vision + camera + follow-ups)
- [x] Vision mode (triage, medication ID, document scan)
- [x] Vision + text context combined in pipeline
- [x] vstash chunk_size=2048 for medical content
- [x] 201 training cards across 15 topics
- [x] E2E test suite (22 cases)
- [x] Model benchmark (24 scenarios x 8 models)
- [x] Tested: E2B, E4B, Qwen 4B/9B, Gemma 31B, Flash Lite/Flash/Pro
- [x] Bilingual verified (ES, FR, SW, HA, PT, AR, HI, AM)
- [x] CLAUDE.md, README, constitution, roadmap, sources plan
- [x] Repo private on GitHub

### Benchmark Results
```
Model             Pass Rate   Avg Time   Safety   Clinical
Gemma E2B             71.4%      5.3s      5/6       7/10
Gemma E4B             76.2%      8.8s      6/6       7/10
Qwen 3.5 9B           90.5%     18.6s      6/6      10/10
```
- E4B: minimum viable for on-device generative mode
- Qwen 9B: best quality, same architecture
- E2B: too small for safety-critical generation

---

## Next Steps (Priority Order)

### P0 — Fix Before Hackathon Submission

1. **Error handling in vision pipeline**
   - What: Add try/catch, user-visible error messages when LLM doesn't support vision, image is corrupt, or model is unloaded
   - Where: `vision.py`, `web.py` (JS error display)
   - Why: Silt flagged — silence is suspicious

2. **Medication ID pipeline completion**
   - What: After identifying drug from photo, search Essential Medicines protocol for dosing, interactions, contraindications
   - Where: `vision.py:identify_medication()` → add consult step
   - Why: Currently extracts drug name but doesn't look up clinical info

3. **Retrieval gap: symptom → disease bridging**
   - What: Protocols titled by disease ("Malaria Treatment") don't match symptom queries ("fever intermittent chills"). E4B needs follow-up, Qwen 9B doesn't.
   - Options: (a) Better titles in protocols, (b) chunk_size tuning, (c) selector mode for E4B
   - Where: `data/core/protocols/` titles, `fever-assessment-imci.md` table
   - Why: Malaria not found for classic malaria symptoms without follow-up

4. **French response broken**
   - What: E4B context overflow on French, JSON truncation
   - Where: Reduce context size or increase model context window
   - Why: Failed in benchmark for both E4B and E2B

### P1 — Hackathon Deliverables

5. **Ingest CHT decision support workflows**
   - What: Download CHT reference apps (medic/cht-core), extract decision trees (JSON/XML), convert to structured markdown, ingest into core.db
   - CHT workflows: maternal health, child health, malaria screening, immunization, etc.
   - Two layers in core.db: WHO protocols (theory) + CHT workflows (field-tested practice)
   - Narrative: "CHT validated these workflows with 40,000 CHWs in 15 countries. MedLocal makes them accessible via natural language + vision + spaced repetition."
   - Caution: Convert to markdown (not raw JSON), validate no conflicts with WHO protocols
   - Reference: https://github.com/medic/cht-core

6. **Kaggle notebook demo**
   - Full workflow: ingest → consult → vision → train cycle
   - Include benchmark results table
   - Show multilingual examples
   - Honest limitations section

6. **Video demo (optional but strong)**
   - Phone screen recording: open browser → ask question → get answer → take photo → follow up
   - 2-3 minutes max

7. **Pre-built core.db for distribution**
   - Ship the SQLite with all 54 protocols pre-ingested
   - User just installs + runs, no ingestion step

### P2 — Post-Hackathon

8. **Selector mode for E2B**
   - Gemma selects best pre-written answer instead of generating
   - Zero hallucination by design
   - Makes E2B viable for phone deployment

9. **Formulary protocol (drug interactions/dosing)**
   - Extract from MSF Essential Drugs Guide (663 pages)
   - Enable medication photo → full drug info lookup

10. **PWA with service worker**
    - Install to homescreen, offline-first
    - Push notifications for training reminders

11. **Multi-language protocol packs**
    - French, Portuguese, Swahili, Arabic translations of core protocols
    - Improves retrieval for non-English queries

12. **Field testing with CHW organization**
    - Partner with MSF, WHO, or local NGO
    - Real-world validation

---

## Architecture Notes

### What Works
```
CHW question → vstash (chunk_size=2048) → top 4 protocols → LLM structured output → safety checks → response
```

### What Doesn't Work
- Consultation index (false positive contamination) — REMOVED
- Diagnostic keyword expansion (hidden hallucination) — REVERTED to symptom-only
- Specific safety rules (creates bias) — REVERTED to generic rules
- E2B for generative mode (fails safety) — E4B minimum

### Model Tiers
| Tier | Model | Use Case |
|------|-------|----------|
| Phone (future) | E2B | Selector mode only |
| Phone/Tablet | E4B | Generative consultation (minimum viable) |
| Laptop | Qwen 3.5 9B | Best quality, same architecture |
| Cloud baseline | Gemini Flash | Gold standard for comparison |
| Teacher | Gemini Flash | Training card + index generation (offline) |
