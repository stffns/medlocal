# MedLocal - Roadmap

## Key Insights from Genesis Conversation

### Architecture Decisions
1. **vstash IS the knowledge** - Gemma no necesita "saber" medicina. El conocimiento vive en vstash, el modelo solo razona sobre contexto recuperado.
2. **Teacher offline, Judge on-device** - Modelo grande genera Q&A pairs una vez. Gemma solo evalua respuestas contra respuestas conocidas.
3. **Core cerrado + Local abierto** - Seguridad medica. Core WHO no se toca. Local para protocolos nacionales/regionales.
4. **Web local, no app nativa** - FastAPI + HTML sirve a cualquier dispositivo con navegador.
5. **Domain-agnostic** - La arquitectura sirve para cualquier vertical. Medico es el primero.

### Lessons Learned (composite, 2026-04-04 through 2026-04-09)
1. **Consultation index WORSENED quality** - Q&A pairs caused false positive matches (measles from fever alone). Removed. Raw protocols + clean retrieval + capable model is the winning formula.
2. **chunk_size=2048 and ≤1 H2 per file are load-bearing** - vstash chunks at every markdown header BEFORE checking size, so a file with five `##` produces five independently-ranked fragments. 64 of 67 protocols had to be flattened to bold-labels structure during the 2026-04-08 session. Every protocol now produces exactly one chunk.
3. **Keyword expansion must NOT diagnose** - Only translate symptoms to clinical terms. Diagnostic expansion is hidden hallucination in the retrieval pipeline.
4. **E2B is viable with the right pipeline (retraction of the earlier draft).** The 2026-04-04 draft of this list said "E2B is not viable for the consult path because it fails drug allergy safety". That observation was correct for E2B with a naive prompt - but with the PRIORITY 0 allergy guardrail (Capa I, landed 2026-04-09 as commit `33f5edb`), E2B scores **101/101** on the 101-case judged benchmark, tied with E4B. The pipeline is the determinant of clinical safety across the 2B-4B range, not the model size. The E2B vs E4B gap is about response richness, not viability.
5. **"Bigger model != safer" retraction.** The 2026-04-04 draft claimed "Gemini Pro failed the allergy test" as evidence that bigger is not automatically safer. The 2026-04-09 LLM-as-judge audit found that the alleged Gemini failures were harness wording artefacts, not clinical errors. Gemini 3.1 Pro with a naive prompt scores 100/101 on the same suite (the single residual HP03 is also a wording artefact). The retraction is documented in the hackathon writeup §5.4.
6. **Structured JSON output via schema** - Forces model to name condition, list actions. Eliminates vague assessments.
7. **Protocol refs in output** - Small models inject "Protocol ID 1" despite instructions. Fixed with `_clean_protocol_refs()` post-processing.
8. **Vision needs CHW context** - Image alone insufficient for diagnosis. CHW text combined with visual findings produces correct results.
9. **Continuous testing after every protocol change** - Adding a protocol shifts the MMR/RRF ranking for every other case. The 2026-04-09 pneumonia safety-floor addition silently regressed DA05 (malaria dose) from PASS to FAIL because cross-protocol weight-band content confused the small model's band-boundary reasoning. Fix: every KB edit now requires a full bench re-run, not spot-checking the target case. See commit `d07a90f` and the feedback_continuous_testing memory.
10. **Silent wrong is worse than loud wrong** - The 2026-04-08 Silt review session found four silent failure modes (JSON parse into empty dict, dose authority check asleep, whack-a-mole negation regex, cross-lingual emergency gap). Fix in each case was adding a deterministic second check behind the first. The safety layer is now "loud by default" - when something fails, it announces itself through `SafetyFlag`, the audit log records it, and the CHW sees a refusal instead of a silent empty answer.

---

## Current State (2026-04-09)

### Completed
- [x] **73 clinical protocols** (WHO/MSF/UNICEF/AAP sourced, single-chunk, validated by `medlocal protocol audit`)
- [x] **28 CHT decision-support workflows** (PIH Malawi + default reference app)
- [x] **9-layer anti-hallucination safety pipeline** - Capa A (emergency regex) through Capa I (PRIORITY 0 allergy guardrail, landed 2026-04-09)
- [x] **PRIORITY 0 allergy guardrail** - extract user-reported allergies before LLM call, inject hard prompt constraint, post-process backstop that overrides the answer if the model slips. Twenty-one unit tests.
- [x] `_flag()` helper for safety flag dedup
- [x] **Structured JSON output** via schema (forces condition naming)
- [x] **Pre-flight translator** - single structured call classifies scope + emergency before retrieval
- [x] **4-pass `_multi_query_search`** - raw + English expansion + preflight terms + FTS-only safety net
- [x] **FTS-boosted hybrid retrieval** (`vec_weight=0.3, fts_weight=0.7, mmr_lambda=1.0`) via direct `_store.search`
- [x] **LLM-as-judge evaluator** - two-layer harness (regex fast path + Gemini 2.5 Flash judge for ambiguous cases). Verdicts cached at `tests/.judge_cache.json` for byte-deterministic reruns.
- [x] Teacher/Judge LLM separation in config
- [x] Unified web UI (consult + vision + camera + follow-ups)
- [x] Vision mode (triage, medication ID, document scan)
- [x] Vision + text context combined in pipeline
- [x] **101-case comprehensive benchmark** (15 categories, release gate, ~30 min on E2B)
- [x] **20-case smoke suite** (dev loop, ~5 min)
- [x] **79 unit tests** in `tests/test_unit.py` covering JSON repair, negation detection, emergency detection, controlled drug guard, allergy extraction + detection, runtime check, structured LLM parse error
- [x] Bilingual verified (EN, ES, FR, PT, SW, HI, AR)
- [x] **Kaggle Tier A demo notebook** (`notebooks/medlocal_demo.ipynb`, landed 2026-04-09) - seven representative cases, switched to Gemma 4 (`gemma-4-26b-a4b-it`) as the cloud-demo consult LLM so the demo is thematically consistent with the Gemma 4 Good Hackathon
- [x] **Hackathon writeup honest rewrite** (`docs/HACKATHON-WRITEUP.md`) - §5.4 retraction of the earlier Gemini overclaims, §5.6 manual audit of every residual, §5.7 scope-and-limits, §9 elevation of Android APK as the headline next step
- [x] **AI-assistance disclosure** - Acknowledgments sections in README, writeup, and notebook framing the author as protagonist
- [x] README, constitution, ARCHITECTURE, PIPELINE, ROADMAP, SOURCES, CHANGELOG refreshed to the 2026-04-09 state
- [x] **13 commits pushed to `origin/main`** during the 2026-04-09 sprint

### Benchmark Results (2026-04-09 final, LLM-judge verified)

| Config | Score | Avg latency | Offline |
|---|---|---|---|
| **Gemma 4 E4B + MedLocal + judge** | **101/101 (100 %)** | 29 s | ✅ laptop (llama.cpp Q4_K_S, ctx=12000) |
| **Gemma 4 E2B + MedLocal + judge** | **101/101 (100 %)** | **19 s** | ✅ phone-class memory profile, tested on laptop |
| **Gemini 3.1 Pro + naive + judge** | 100/101 (99 %) | 17 s | ❌ cloud (HP03 wording artefact, not clinical error) |

Both Gemma on-device configurations are **clinically safe on this suite**. The pipeline is the determinant across the 2B-4B range, not the parameter count. The E2B vs E4B choice is about response richness, not safety. Gemini 3.1 Pro is clinically excellent on every case; what it cannot provide are the deployment properties the cloud model structurally cannot match - offline operation, source-grounded verifiability, and editability without retraining. **The numeric story is an effective tie; the architectural story is where the comparison lives.**

---

## Next Steps (Priority Order)

### The one that matters most

**1. Android-native MedLocal APK running Gemma 4 E2B entirely on-device.** This is the single work line that turns the proof-of-concept into the product. A community health worker in rural Mali pulls a $50 Android phone out of a pocket, types a question in French or Swahili, and gets a source-cited clinical recommendation in under 30 seconds **without ever touching the network**. Everything else on this list is instrumentation, packaging, protocol authoring, or evaluation breadth. The Kaggle Gemma 4 Good Hackathon judges care about exactly this deployment target.

Three plausible build paths, in rough order of engineering effort:
- **Path A - WebView + FastAPI foreground service.** Bundle the existing Python FastAPI server as an Android Foreground Service, ship the pre-built `core.db` and the GGUF in the APK assets, run `llama.cpp` as a native library via JNI. Least code reuse risk, maximum direct path from the hackathon code to the phone. Weekend-scale once the build toolchain is set up.
- **Path B - MediaPipe LLM Inference + thin Kotlin wrapper.** Google's MediaPipe LLM Inference API lists Gemma 4 as a first-class supported model. Wrap `consult()` behaviour in a Kotlin service. Better performance and thermal behaviour than Path A on commodity phones; more code to write.
- **Path C - llama.cpp compiled for ARM + Jetpack Compose UI.** Maximum control, maximum polish, most Kotlin-native. Weeks of work, cleanest phone-first codebase, the option to ship as a proper Play Store app.

**Status: not yet started.** The architectural runway is built; the takeoff is the APK.

### P0 - Submission deliverables (landed)

2. ✅ **Hackathon writeup honest rewrite** (`docs/HACKATHON-WRITEUP.md`, commit `b2f5180` and subsequent refinements). §5.4 retraction of earlier Gemini overclaims, §5.6 manual audit of every residual, §5.7 scope-and-limits.
3. ✅ **Kaggle Tier A demo notebook** (`notebooks/medlocal_demo.ipynb`, commits `38b28a8` → `56eb58d`). Seven representative cases, six in English and one deliberately in French for cross-lingual demonstration, switched to Gemma 4 (`gemma-4-26b-a4b-it`) as the cloud-demo consult LLM.
4. ✅ **LLM-as-judge evaluator** (commit `6e93cc0`). Two-layer harness, cached verdicts, closed the regex wording artefacts that contaminated the earlier Gemini baseline.
5. ✅ **PRIORITY 0 allergy guardrail** (commit `33f5edb`). Closed the E2B ST04 non-deterministic failure.
6. ✅ **Continuous-testing rule** (commit `d07a90f` + feedback memory). Every KB edit requires a full bench re-run.
7. ✅ **AI-assistance disclosure** (commit `b58963b` + later revisions). Protagonist framing across README, writeup, and notebook.

### P1 - Close to ship with the APK

8. **Pre-built `core.db` for distribution.** Ship the SQLite with all 73 protocols pre-ingested so the end user downloads, installs, and runs offline in three commands. Prerequisite for item 1 - the APK bundles a pre-ingested snapshot rather than running ingest on the phone at first launch.
9. **Ollama deployment recipe** (`docs/HOWTO-DEPLOY.md`). Modelfile template (`num_ctx=12000`, `temperature=0.0`, JSON-schema retry logic). An alternative deployment story for reviewers whose workflow is Ollama-first.
10. **300-case field validation suite** authored in consultation with practicing CHWs and clinical supervisors from at least three low-resource regions. Named in the hackathon writeup §5.7 as the single biggest gap to deployment readiness. The 101-case suite we have is adversarial and auditable but was authored by one person with AI reviewers; deployment-grade validation requires breadth from the people who will actually use the system.
11. **Protocol authoring guide** (`docs/HOWTO-PROTOCOL-AUTHORING.md`). Rules: ≤1 `##` per file, worked examples at every band boundary (DA05 lesson), explicit negation cues for the wrong answer, single-chunk bounded, WHO/MSF source cited, `medlocal protocol validate` green before merge, full bench re-run before merge.

### P2 - Post-hackathon

12. **Intimate-partner violence protocol** - parallel to child protection, based on WHO RESPECT women framework and the LIVES protocol. Adult safeguarding is the missing companion to CP01.
13. **Vision triage text-reading pass.** Add an OCR-intent prompt before scene description so photos of medication packages produce drug identification, not scene descriptions. Pending from the 2026-04-07 backlog.
14. **Capa C nominalization gap fix.** The preflight LLM sometimes returns nominalised forms ("inability to drink") where the Capa A regex only matches verb forms ("unable to drink"). Currently Capa C catches zero cases that Capa A or Capa B do not already catch, so the gap is theoretical, but worth closing before a future cross-lingual edge case surfaces it.
15. **Selector mode for Gemma E2B.** The model picks a pre-written answer from the consultation index instead of generating one. Less urgent now that the generative path is 101/101, but still interesting as a second architectural option where response latency matters more than flexibility.
16. **Upstream remaining retrieval fixes into vstash.** Four landed in vstash 0.26.0 during the sprint; the rest of the backlog is in `memory/project_retrieval_insights.md`.
17. **PWA with service worker.** Install to homescreen, push notifications for training reminders. A lighter alternative to the native APK if the APK toolchain becomes a blocker.
18. **Multi-language protocol packs.** French, Portuguese, Swahili, Arabic translations of core protocols. Improves retrieval for non-English queries beyond the current 7-language coverage.
19. **Field testing with a CHW organisation.** Partner with MSF, WHO, or a local NGO for a supervised real-world pilot. The 300-case validation suite (item 10) is a prerequisite.

---

## Architecture Notes

### What Works - 9-layer pipeline (2026-04-09)

```
CHW question → _extract_search_query
            → extract_allergies (PRIORITY 0, Capa I) → inject hard prompt constraint
            → detect_emergency (Capa A, regex fast path)
            → preflight (Capa B, scope + cross-lingual emergency classification)
            → detect_emergency on preflight.clinical_terms (Capa C, safety net)
            → _multi_query_search (Capa D, 4 passes including FTS-only safety net)
            → relevant[:6] → chat_structured (Capa E, JSON schema)
            → check_dosages (Capa F, value cross-check)
            → check_controlled_drugs (Capa G, dose authority)
            → StructuredLLMParseError → graceful refusal (Capa H)
            → check_allergies_in_answer (Capa I post-process, override if allergen slipped)
            → audit.log
            → structured response to mobile UI
```

See `docs/PIPELINE.md` for the full deep dive. The body of that
document describes the 2026-04-07 architecture; the Capa G / Capa I
additions and the LLM-judge evaluator are documented in §5 and §11
of PIPELINE.md (updated 2026-04-09) and in §6 of the hackathon
writeup.

### What Doesn't Work
- Consultation index (false positive contamination) - REMOVED
- Diagnostic keyword expansion (hidden hallucination) - REVERTED to symptom-only
- Specific safety rules (creates bias) - REVERTED to generic rules
- **Spot-checking the target case after a protocol change** - the DA05 malaria regression proved that a protocol addition can silently regress unrelated cases via MMR/RRF ranking shift. The rule is "full bench re-run before merge", not "confirm the new protocol fixes the target case". See commit `d07a90f` and the continuous-testing feedback memory.
- **Non-explicit weight band boundaries in dose protocols** - small models misread the edges ("is 12 kg in the 5-14 band or the 15-24 band?"). Fix: worked examples inside every band, explicitly naming the boundary values.
- **Prompt hope for user-reported constraints** - allergies live in the question, not in any protocol. Trusting the prompt alone to propagate the constraint is not a safety layer. Fix: extract before the LLM call, inject a hard constraint, post-process and override. PRIORITY 0 allergy guardrail.

### Deployment Tiers (2026-04-09)

| Tier | Model | Use Case | Status |
|------|-------|----------|--------|
| Phone (target) | Gemma 4 E2B | Full generative consultation, offline, source-cited | Memory profile validated on laptop; APK not yet built (item 1 above) |
| Phone / tablet (tested) | Gemma 4 E2B | Full generative consultation, offline, source-cited | **101/101** on laptop with ctx=12000, Q4_K_S |
| Tablet / laptop | Gemma 4 E4B | Full generative consultation with richer response style | **101/101** on laptop with ctx=12000, Q4_K_S |
| Cloud reference | Gemini 3.1 Pro | Baseline comparison for the writeup | 100/101 with naive prompt (HP03 wording artefact) |
| Cloud demo (Kaggle) | Gemma 4 26B-a4b-it | Kaggle notebook consult LLM (Gemini API) | Thematically consistent with the Gemma 4 hackathon |
| Teacher / judge | Gemini 2.5 Flash | LLM-as-judge evaluator + training card generation (offline) | Cached verdicts in `tests/.judge_cache.json` |
