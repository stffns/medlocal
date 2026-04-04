# MedLocal — Roadmap

## Key Insights from Genesis Conversation

### Architecture Decisions
1. **vstash IS the knowledge** — Gemma no necesita "saber" medicina. El conocimiento vive en vstash, el modelo solo razona sobre contexto recuperado. Esto permite usar modelos pequeños (E2B/E4B).
2. **Teacher offline, Judge on-device** — Modelo grande (Claude/GPT-4/Gemini Pro) genera Q&A pairs una vez. Gemma E4B/E2B solo evalua respuestas contra respuestas conocidas. Tarea simple = modelo pequeño.
3. **Core cerrado + Local abierto** — Seguridad medica. Core WHO no se toca. Local para protocolos nacionales/regionales.
4. **Web local, no app nativa** — FastAPI + HTML sirve a cualquier dispositivo con navegador. PWA para produccion post-hackathon.
5. **Domain-agnostic** — La arquitectura sirve para derecho, agricultura, educacion, mantenimiento industrial. Medico es el primer vertical por el hackathon.

### vstash Features que aportan valor directo
- **Temporal scoring** — Protocolos frecuentes suben de ranking (adapta al contexto epidemiologico local)
- **Adaptive gamma** — Zero cold start degradation en deploys nuevos
- **Relevance signal** — "No se, refiera al hospital" > respuesta inventada (puede salvar vidas)
- **MMR dedup** — Cobertura diversa en protocolos largos
- **Context expansion (±1)** — 2.64x mas contexto, pasos que dependen de pasos previos
- **Multi-profile federated** — Core WHO + Local buscan juntos, fuente visible
- **Direct chunk access** — Recall recupera chunk exacto O(1) cuando el trabajador falla una pregunta
- **Journal** — Memoria institucional local ("brote de dengue esta semana")

### Modelo E2B vs E4B
- E2B: 2.3B params efectivos, <1.5GB cuantizado, 3x mas rapido que E4B, corre en telefono de $50
- E4B: 4.5B params efectivos, mas capacidad de razonamiento, necesita mas recursos
- **Estrategia**: Probar ambos como juez. Si E2B mantiene calidad, usar como default. E4B para dispositivos con mas capacidad.
- El dato impactante para hackathon: sistema medico completo en 1.5GB modelo + 50MB knowledge base

### Fuentes de Documentos Medicos
- **MSF Clinical Guidelines** — Manual de campo perfecto para community health workers
- **WHO Essential Medicines List** — Dosificaciones completas
- **WHO IMAI District Clinician Manual** — 800 pags de atencion primaria
- **Hesperian "Where There Is No Doctor"** — Clasico para CHW, Creative Commons
- **WHO guias especificas**: malaria, TB, HIV, neonatal, emergencias
- **DermNet** — Atlas dermatologico open access (para vision mode)
- **Guias nacionales** (Kenya, Colombia, etc.) — Perfil local
- **OpenWHO.org** — Cursos y materiales de capacitacion

---

## Roadmap

### Phase 1 — Core Quality (Current Sprint)
**Goal: Respuestas clinicas confiables con Gemini Flash / Gemma E4B**

- [x] Dual-profile knowledge base (core + local)
- [x] Consultation with structured prompts optimized for small models
- [x] Multi-query retrieval (keyword expansion)
- [x] Judge with few-shot calibration
- [x] Teacher/Judge LLM separation in config
- [x] Gemini 2.5 Flash integration via OpenAI-compatible API
- [x] 6 clinical protocols ingested (diarrhea, malaria, pneumonia, pre-eclampsia, newborn, nutrition)
- [x] Bilingual responses (EN/ES verified)
- [x] 5 WHO PDFs downloaded
- [ ] Download and ingest MSF Clinical Guidelines
- [ ] Download Hesperian "Where There Is No Doctor"
- [ ] Test with Gemma 4 E4B on-device (Ollama/LM Studio)
- [ ] Test with Gemma 4 E2B on-device
- [ ] Compare E2B vs E4B vs Flash quality on same 6 scenarios
- [ ] Add 10+ more clinical protocols (TB, HIV, diabetes, snake bites, burns, first aid)

### Phase 2 — Vision Mode
**Goal: Camera-based workflows for the hackathon demo**

- [ ] Vision engine with 3 workflows (triage, medication ID, document scan)
- [ ] Image input support in llm.py (Gemma 4 multimodal via OpenAI API)
- [ ] `POST /api/vision/triage` — Photo → clinical description → protocol retrieval
- [ ] `POST /api/vision/medication` — Photo → drug ID → interactions/contraindications
- [ ] `POST /api/vision/scan` — Photo → OCR → auto-ingest to local profile
- [ ] CLI commands: `medlocal vision triage`, `medlocal vision scan`
- [ ] Test with real wound/rash images from DermNet
- [ ] Test medication identification with common drug packaging

### Phase 3 — Mobile Web UI
**Goal: Usable interface on a phone screen**

- [ ] FastAPI serves mobile-first HTML (single file, zero build step)
- [ ] 5 tabs: Consult, Chat, Training, Vision, Admin
- [ ] Dark theme, large buttons for field use
- [ ] Camera capture with `capture="environment"` for rear camera
- [ ] Admin panel: add/remove local documents, view stats
- [ ] OFFLINE badge visible
- [ ] Sources marked as [WHO] or [LOCAL]
- [ ] PWA manifest for install-to-homescreen

### Phase 4 — Training Mode Polish
**Goal: Complete spaced repetition loop**

- [ ] Pre-generate card deck with large teacher model (Claude/Gemini Pro)
- [ ] Ship pre-built training.db with cards for all core protocols
- [ ] Judge evaluation with E4B/E2B on-device
- [ ] Progress dashboard (accuracy trends, topics mastered)
- [ ] Weekly/daily study session reminders (PWA notifications)

### Phase 5 — Hackathon Submission
**Deadline: May 18, 2026**

- [ ] Kaggle notebook demonstrating complete workflow
- [ ] End-to-end demo: ingest → consult → vision → train cycle
- [ ] Benchmark comparison table (vstash vs Chroma vs BM25)
- [ ] README with installation, usage, and impact narrative
- [ ] Video demo (optional but strong for judges)
- [ ] Constitution document polished for submission

### Phase 6 — Post-Hackathon (if project continues)
- [ ] Native PWA with service worker for full offline
- [ ] Deepgram voice integration (ask by speaking, hear answer)
- [ ] Multi-language protocol packs (FR, PT, SW, AR)
- [ ] Field testing with actual CHW organization
- [ ] Domain expansion: agriculture, legal, education verticals
- [ ] Distribution model: pre-configured packages per country/organization

---

## Commercial Vision (Post-Hackathon)

**Model: Platform + customization, not SaaS**
- Sell pre-configured core.db packages per domain/country
- Charge for customization of local profile for organizations
- No per-query cost, no subscription, no vendor lock-in
- Target customers: NGOs (MSF, WHO), health ministries, training programs
- Revenue: licensing + professional services for deployment

**Key differentiator**: "We don't modify the model. Clinical protocols come directly from WHO, verifiable, without fine-tuning distortion. The model only reasons about them." — More auditable for medical use.
