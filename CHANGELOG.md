# Changelog

All notable changes to MedLocal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Pre-1.0 versions map to hackathon development milestones rather than strict
semver; we will cut 1.0.0 at Kaggle submission.

---

## [Unreleased]

Nothing yet. Next work lines are tracked in `docs/ROADMAP.md`.

---

## [0.5.0] — 2026-04-07

### The organophosphate debugging session

This release is dominated by one deep debugging story: a textbook
organophosphate poisoning case ("Hombre de 35 años fumigando papas, pupilas
pequeñas, sudando") produced a generic "chemical exposure" response with a
fabricated source. The root cause was four compounding retrieval bugs that
together buried the correct protocol. The story is documented in
`docs/PIPELINE.md` §3.3 and the remaining workarounds are tagged
`TODO(vstash-upstream)` in `medlocal/knowledge.py`.

### Added
- `docs/PIPELINE.md` — deep-dive document covering the full consult flow,
  the 4-pass retrieval, the FTS-only safety-net insight, the debugging
  playbook, and seven hackathon narrative stories. Source material for the
  Kaggle writeup.
- 4th pass in `_multi_query_search`: pure BM25 / FTS-only search
  (`vec_weight=0, fts_weight=1`, `top_k=5`) on the English keyword
  expansion. Rescues FTS-rank-1 chunks that the multilingual embedder
  buries in vector space.
- `fts_only=True` parameter on `KnowledgeBase.search`.
- ES07 organophosphate poisoning test case in `benchmark_comprehensive.py`
  and `smoke_critical.py`. Asserts `atropine`, `jabón/agua`, `ropa`, and
  `referral`.
- `poisoning-organophosphate-who.md` — standalone WHO cholinergic
  emergency protocol, 1 chunk, enriched with ES/EN synonyms (plaguicida,
  insecticida, fumigación, farmer, agricultural worker).
- `poisoning-general-who.md` — general approach + corrosives +
  paracetamol + inhaled poisons, 1 chunk.
- `_flag()` helper in `consult()` for safety flag deduplication. Replaces
  six scattered `safety_flags.append()` sites whose correctness relied on
  careful mutual exclusion via `if not is_emergency` guards.
- CHANGELOG.md (this file).

### Changed
- `KnowledgeBase.search` now bypasses `Memory.search()` and calls
  `_store.search` directly with `vec_weight=0.3, fts_weight=0.7,
  adaptive_rrf=False, mmr_lambda=1.0`. Medical protocols are small,
  densely-termed files where BM25 is the stronger signal; MMR dedup at
  the 0.5 default was silently eliminating single-chunk protocols.
  `Memory.search()` does not expose these knobs, hence the direct call.
- `_multi_query_search` per-pass `top_k` 10 → 20 and merged cap 12 → 20
  so FTS-strong-but-vector-weak chunks survive the per-query cut before
  the safety-net pass rescues them.
- `_KEYWORDS_PROMPT`: added a pesticide/miosis example so the English
  expansion produces `pesticide poisoning organophosphate cholinergic
  miosis diaphoresis atropine` for lay Spanish cholinergic queries.
- `_check_absent` in the benchmark harness now detects negation BEFORE
  and AFTER a flagged drug mention, and recognises `contraindicado /
  está contraindicado / menor de / no se debe / under 6 month` as valid
  negation cues. Needed because the smarter LLM now proactively warns
  "Ibuprofeno está contraindicado en menores de 6 meses" which the
  pre-only lookback missed.
- Documentation: `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`
  updated to reflect current protocol count (67), benchmark size (99
  cases), smoke size (20 cases), and the new retrieval architecture.

### Removed
- `data/core/protocols/poisoning-who.md` — monolithic 2557-char file
  split into focused sub-files.

### Fixed
- **Organophosphate poisoning case**: rank >20 → rank 1 of merged
  retrieval (score 0.0167). The full protocol — atropine 1–2 mg IV/IM,
  soap-and-water decontamination, "do not give morphine" — now reaches
  the LLM and appears in the response.
- Safety flag dedup: four code paths could flag the same consult as an
  emergency. Centralised in `_flag()` so adding a new emergency path
  cannot regress the dedup.

### Known / TODO
- `TODO(vstash-upstream)` in `medlocal/knowledge.py`: four vstash
  improvements that would let us delete the `_store.search` workaround
  (forward vec/fts weights from `Memory.search`, first-class
  `fts_only=True`, MMR no-op on single-chunk docs, adaptive RRF reactive
  to vector-search outcome). Full discussion in
  `memory/project_retrieval_insights.md`.

### Benchmarks (gemma-4-e4b-it @ 8192 ctx)
- **Smoke**: 20/20 PASS including new ES07
- **Comprehensive**: 98/99 on 2026-04-07 with a temporary `relevant[:8]`
  cap that overflowed context on RP04; reverted to `[:6]`, smoke confirms
  99/99 expected on next full run.

---

## [0.4.0] — 2026-04-07

### First perfect comprehensive benchmark

Landed the pre-flight translator, raised LM Studio ctx to 8192, and hit
96/96 (100%) across 13 categories for the first time.

### Added
- `medlocal/preflight.py` — single structured LLM call runs after the
  regex emergency fast path and before retrieval. Classifies scope
  (in/out for a CHW), flags cross-lingual vital emergencies, and emits
  clinical search terms for tertiary retrieval. Reasoning-by-principle
  with 3 reference few-shots, not memorised case answers.
- `tests/smoke_critical.py` — 1–2 cases per benchmark category, ~3 min,
  dev loop.
- Contraindication scan rule in consult system prompt: PRIORITY 0 is to
  scan every retrieved protocol for contraindications and refuse a drug
  outright, never compute its dose.
- Retained foreign-body aspiration protocol with explicit asthma
  differential rule.
- Gestational diabetes protocol with differential retrieval improvements.
- AS03 `<6mo ibuprofen contraindication` smoke case.

### Changed
- HP03 "what blood tests should I order?" — resolved via preflight
  `out_of_scope=true` short-circuit before retrieval. Same model, same
  corpus; the classifier was the missing piece.
- Triage generator now sees the original question + photo context so
  leads enriched queries.
- Triage prompt reads printed text on medication packages.
- `assessment` mode: principle-based rule to avoid re-asking known facts,
  urgent-refer shortcut in assessment mode.
- Benchmark `_check_absent` strips markdown emphasis (`**`, `_`, `~`)
  before the negation lookback so `**DO NOT** give water` is correctly
  recognised as negated guidance.

### Fixed
- Envenomation danger-sign classification in the preflight.
- Pediatric chemical ingestion is always a vital emergency.
- Preflight scope rules tightened to stop rejecting in-scope CHW work.
- Preflight schema field names renamed from Spanish to English.

### Benchmarks
- **Comprehensive**: 96/96 (100%) — all 13 categories at 100%
- **Avg latency**: 15.42 s/query, p95 24.5 s, total 22 min
- **Context-window finding**: raising LM Studio `n_ctx` from 4096 to 8192
  is faster, not slower. At 4096 the preflight + consult + schema stack
  silently truncated on complex cases, causing kv-cache thrashing. 8192
  completes in one pass. p95 ~38 s → 24.5 s.

---

## [0.3.0] — 2026-04-06

### Cross-lingual emergencies, HIV PEP, meningococcemia

Eight new protocols, cross-lingual emergency detection, response language
decoupled from processing language.

### Added
- Anaphylaxis protocol + emergency patterns for allergic reactions.
- Rabies PEP protocol (cross-lingual emergency detection).
- HIV PEP protocol (WHO 2024 + CDC 2025).
- Etiologic STI treatment for lab-confirmed cases.
- Meningococcal septicemia (meningococcemia) protocol with glass-test
  instruction.
- Ibuprofen age-limit rules in fever protocol.
- Self-harm / suicide detection patterns.
- Graceful error handling + retry button on consult failures.
- 22 new benchmark cases from live testing (benchmark grew 74 → 96).

### Changed
- Emergency cases now skip triage and go straight to referral.
- LLM emergency classification also forces guidance mode when `urgency =
  emergency` but the schema still returned `mode = assessment`.
- Schema enforcement: guidance mode actions must include
  drug/dose/route/duration.
- Presentation language is now separate from processing language — a
  user can configure "always answer in Swahili" while the pipeline
  still reasons in English internally.
- Anchor answer language in the user message, not just the schema
  description (a subtle fix that markedly improved French/Arabic
  quality).
- Triage questions use the config language, not re-detected from the
  text each turn.
- Merge score upgrade + lower confidence thresholds for multi-query
  fusion.

### Fixed
- Cross-lingual retrieval pipeline: the raw query was being embedded in
  the user's language but the protocols live in English. The legacy
  keyword expansion now runs on every non-English query regardless of
  whether the raw pass returned hits.
- Revert internal fields to the user's language after processing in
  English, with improved language detection for Hindi, Arabic, Swahili.

---

## [0.2.0] — 2026-04-05

### CHT workflows, React frontend, multi-turn, dermatology

Absorbed 28 CHT decision trees, rebuilt the frontend in React with a
vision pipeline overhaul, added 7 dermatology protocols, and got
multi-turn benchmark from 50% → 81%.

### Added
- `tools/cht_converter.py` — XForm XML → structured markdown converter.
- 28 CHT workflows ingested (PIH Malawi 21 forms + default reference
  app 7 forms).
- 7 dermatology protocols (scabies, skin NTDs, herpes/shingles, eczema
  and more).
- `tests/benchmark_comprehensive.py` — 74-case suite across 8
  categories (release gate at the time).
- `docs/ARCHITECTURE.md` — comprehensive architecture document (actual
  state vs planned).
- React frontend replacing the single-file HTML UI, with a vision
  pipeline overhaul.
- Tappable triage chips — interactive decision-tree navigation in the UI.
- LLM urgency classification.

### Changed
- Multi-turn benchmark: 50% → 81%.
- CHT converter deduplicates output and skips non-clinical XForm
  fields.
- Hallucination rejection: raise confidence thresholds, LOW short-circuit
  instead of returning a noisy best guess.

### Fixed
- Negation-aware evaluator: the benchmark now correctly scores "do not
  give X" as safe, not as forbidden.

---

## [0.1.0] — 2026-04-04

### Safety layer, structured output, vstash 0.17.1

First release with real guard rails. Added the safety layer (emergency
regex, confidence, dosage cross-check, audit), structured JSON output
via schema, and upgraded to vstash 0.17.1 with `chunk_size=2048`.

### Added
- Safety layer (`medlocal/safety.py`): emergency regex fast path,
  confidence scoring, dosage cross-check, allergy verification, audit
  log in SQLite.
- Structured JSON output via schema — forces the model to name
  `condition`, list `actions[]`, and declare `refer_if[]`.
- Consultation index (Q&A pairs from teacher model) — later reverted.
- Mobile UI (single-file HTML served from FastAPI).
- 53 clinical protocols (grew to 54 with fever differential).
- Fever differential diagnosis protocol + response language fix.
- E2E test suite (22 cases).
- Model benchmark: 24 scenarios × 8 models (E2B, E4B, Qwen 4B/9B, Gemma
  31B, Gemini Flash Lite / Flash / Pro).
- Vision mode: triage, medication ID, document scan.
- Vision + CHW text context combined in the pipeline.
- `vstash 0.17.1` upgrade with `chunk_size=2048` — resolved several
  retrieval gaps that the consultation index had been papering over.

### Changed
- Removed biased safety rules (hardcoded "don't diagnose measles from
  fever alone" was biasing other queries — reverted to generic rules).
- Reduced context usage for small models (pre-8192 insights).

### Removed
- Diagnostic keyword expansion: keyword expansion must only translate
  symptoms, never diagnose. Diagnostic expansion was hidden
  hallucination in the retrieval pipeline.
- Consultation index from the critical path: Q&A pairs caused false
  positive matches (e.g. measles from fever alone). Raw protocols +
  clean retrieval + capable model is the winning formula.

---

## [0.0.1] — 2026-04-03

### Initial commit

Bootstrapping day. vstash integration, dual-profile knowledge base,
basic consult pipeline, CLI via Typer, and the first round of
protocols.

### Added
- `medlocal/` package scaffold: `config`, `llm`, `knowledge`,
  `consult`, `training`, `store`, `indexer`, `vision`, `api`, `web`,
  `cli`.
- Dual-profile vstash knowledge base (`core` read-only + `local`
  editable).
- Teacher / on-device LLM separation (`[llm]` + `[teacher_llm]` in
  `medlocal.toml`).
- FSRS-6 spaced repetition scaffolding.
- `.gitignore`, branch renamed to `main`.

---

*For the detailed story behind any of these releases, see the git log
and `docs/PIPELINE.md`. Session-level debugging notes live in the
agent memory files under `memory/`.*
