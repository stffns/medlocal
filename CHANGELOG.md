# Changelog

All notable changes to MedLocal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Pre-1.0 versions map to hackathon development milestones rather than strict
semver; we will cut 1.0.0 at Kaggle submission.

---

## [Unreleased] — 2026-04-09 hackathon-ready sprint

Candidate for version 0.7.0. Entire day of work driven by manual
testing, honest residual audits, and the continuous-testing rule.
The numeric result is 101/101 on both Gemma configurations and
100/101 on the Gemini 3.1 Pro naive baseline (HP03 harness
artefact). The architectural result is a ninth defense layer, a
two-layer evaluation harness, five new protocols, and a hackathon
writeup that has retracted every overclaim the earlier draft made.

### Added — evaluation harness

- **LLM-as-judge fallback for must_not_contain and check_emergency**
  (`tests/judge.py`, commit `6e93cc0`). Two-layer evaluator: regex
  fast path for the 90 % of cases a regex can decide, Gemini-2.5-
  Flash judge for the ambiguous 10 %. Verdicts cached in
  `tests/.judge_cache.json` for byte-deterministic reruns.
  `benchmark_comprehensive.py` and `benchmark_baseline.py` both gain
  a `--use-judge` flag. The judge cleared 6 Gemini residuals that
  the earlier regex-only run had misinterpreted as clinical failures
  — the retraction is documented in the hackathon writeup §5.4.
- **Cross-lingual URGENT_CUES** in `benchmark_baseline.py` — French
  (urgence, immédiate), Portuguese (urgentemente, imediatamente),
  and Swahili (haraka, dharura) keywords added so the regex
  pre-check does not falsely flag cross-lingual emergency responses.
- **21 new unit tests** covering allergy extraction and detection
  in `tests/test_unit.py`, bringing the total to 79.

### Added — safety layer

- **PRIORITY 0 allergy guardrail** in `medlocal/safety.py` and
  `medlocal/consult.py` (commit `33f5edb`). Ninth defense layer
  (Capa I). `extract_allergies()` parses the question for
  English / Spanish allergy markers with denial backoff, matches
  against a 13-drug alias table with class bridging (penicillin
  → amoxicillin → ampicillin, sulfa → cotrimoxazole, etc.). When
  allergies are found, a hard constraint is injected into the
  system prompt. `check_allergies_in_answer()` runs after
  generation with the same pre-negation backoff pattern as the
  controlled-drug guard and overwrites the answer with a safety
  refusal if any allergic drug is still mentioned.
  `SafetyFlag.ALLERGY_VIOLATION` is raised to the audit log.
  Closes the E2B ST04 non-deterministic failure.

### Added — protocols (corpus 68 → 73 files)

- **`medications-pregnancy-safety-who.md`** (commit `e1ad625`).
  Contraindicated drugs by trimester: aspirin ≥300 mg and all
  NSAIDs after week 28-30, ACE inhibitors and ARBs any trimester,
  warfarin, misoprostol, methotrexate, tetracyclines after week
  15, fluoroquinolones, retinoids. Safer alternatives and the
  red-flag presentation rule for a pregnant woman with preeclampsia
  symptoms who has taken NSAIDs.
- **`infant-safety-home-remedies-who.md`** (commit `4bc05d5`).
  Honey under 12 months (infant botulism), plain water under 6
  months (hyponatremia), whole cow's milk under 12 months, herbal
  infusions caution including star anise neurotoxicity, OTC cough
  and cold medicines under 2 years (AAP/FDA advisory), unmeasured
  home ORS. Safe cough management in young infants with the under-
  3-month-urgent-referral rule.
- **`medication-side-effects-expected-vs-alarm-who.md`** (commit
  `5c1066b`). The expected-vs-alarm decision reference. Ten drugs
  with benign expected side effects a CHW must reassure patients
  about (rifampicin orange urine, iron black stool, metronidazole
  metallic taste, isoniazid tingling, chloroquine pruritus, ACT
  dizziness, etc.). Eight alarm patterns that require STOP and
  refer (jaundice on TB drugs, ethambutol optic neuritis,
  SJS/TEN/DRESS, NSAID bleeding, aminoglycoside toxicity, C. diff
  colitis, efavirenz psychiatric changes, lactic acidosis).
  Dedicated pediatric section: metoclopramide <1 year FDA
  contraindication, chloramphenicol grey baby syndrome in neonates,
  aspirin Reye, ibuprofen <6 months, gentamicin monitoring,
  tetracyclines <8 years, fluoroquinolone cartilage, ceftriaxone
  + calcium in neonates, codeine and tramadol <12 years.
- **`drug-rash-severity-who.md`** (commit `5c1066b`). Three-band
  severity grading (mild / moderate / severe) with appearance,
  action, and re-challenge policy for each band. The severe band
  names anaphylaxis, SJS, TEN, DRESS, and fixed drug eruption.
  Eight red flags (mucous membranes, Nikolsky, fever + antibiotic,
  facial swelling, eosinophilia, lymphadenopathy, late-onset 2-6
  week rash, organ symptoms) escalate any rash to severe.
  Explicit clarification that the common amoxicillin day-5-to-10
  rash is often EBV-associated and is NOT a lifelong penicillin
  allergy.

### Changed — protocols

- **`pneumonia-imci.md`** (commit `e1ad625`). Added a "Weight-only
  safety floor" section: if the CHW reports only the weight and
  the child weighs ≤5 kg, treat as a young infant until proven
  otherwise, refer urgently with IM ampicillin + gentamicin
  pre-referral, do NOT start outpatient oral amoxicillin.
- **`preeclampsia-who.md`** (commit `e1ad625`). Disambiguated the
  low-dose 75 mg preventive aspirin from the analgesic dose ≥300 mg
  which is contraindicated in pregnancy. Cross-reference to the
  new pregnancy medication safety protocol.
- **`malaria-who.md`** (commit `d07a90f`). Rewrote the dosing
  section with explicit boundary examples so a 12 kg child
  appears literally in the 1-tablet-per-dose band. Closes the
  DA05 regression that surfaced from the 2026-04-09 bench run
  after the other protocol additions shifted MMR/RRF ranking.
- **`fever-assessment-imci.md`** (commit `5c1066b`). Added a
  "Comfort Measures When Antipyretics Are Not Available or
  Contraindicated" section with tepid sponging technique
  (explicitly NOT cold, NOT alcohol), decision rules for when
  comfort measures alone are sufficient, and ten refer-even-
  without-antipyretic criteria.

### Changed — harness

- **ST04** in `benchmark_comprehensive.py` (commit `e1ad625`).
  The old `must_contain` required cold-bath / sponging keywords,
  which WHO/IMCI explicitly contraindicates. Rewrote to accept
  any WHO-aligned interim measure (referral, light clothing,
  increased fluids, SRO) while keeping the allergy
  `must_not_contain` intact.

### Added — documentation

- **Hackathon writeup rewrite** (`docs/HACKATHON-WRITEUP.md`,
  commit `b2f5180`). 654 insertions, 263 deletions. Replaces the
  "beats Gemini by 5 points" framing with the honest effective-tie
  numbers. Retracts the false claims the earlier draft made about
  Gemini 3.1 Pro failing XE03 (French IMCI), DA02 (measles Vitamin
  A schedule), and AX03 (bee sting qualifier reasoning) — all
  turned out to be harness wording artefacts under manual audit.
  New §5.3 dual reporting (regex vs judge), §5.6 manual audit of
  every residual with judge verdict text, §5.7 scope and limits
  ("101 cases is a proof of concept, not a deployment
  validation"), and §6 2026-04-09 follow-up covering findings 5-7.
  §10 conclusion reframed as "deployment properties the cloud
  model structurally cannot provide, not a clinical accuracy
  lead". Jay's verdict quote preserved verbatim as the closing
  thesis.
- **§3 writeup — ninth layer** (commit `756800e`). "The 8-layer
  defense" renamed "The 9-layer defense" with Capa I added to the
  ASCII diagram and a new paragraph describing the allergy guard's
  defense-in-depth pattern. Stale protocol counts (69, 70) updated
  to 71 and later to 73 as the corpus grew.
- **Acknowledgments sections** in `README.md` and
  `docs/HACKATHON-WRITEUP.md` (commit `b58963b`). Explicit
  disclosure of AI-assisted development by Claude (Anthropic)
  with the clarification that architectural decisions, clinical
  protocol sourcing, benchmark design, safety-layer specification,
  and evaluation methodology were authored and verified by the
  human author, and that clinical error remains the author's sole
  responsibility.
- **Stale-placeholder documentation pass** (this commit). Updated
  corpus counts in `README.md`, `docs/ROADMAP.md`, `docs/SOURCES.md`
  ("Current State (69 → 73 files)"), and the
  `docs/PIPELINE.md` last-updated block. `CHANGELOG.md` expanded
  to capture the full 2026-04-09 sprint.

### Removed

- **`CLAUDE.md`** from the tracked repository (commit `b58963b`).
  The tool-specific agent config file is now in `.gitignore`
  alongside `.claude/` and lives only in the author's local
  development environment. Cross-references removed from
  `README.md`, `docs/ARCHITECTURE.md`, and `docs/ROADMAP.md`.
  Historical mentions in earlier `CHANGELOG.md` entries left
  intact as dated release records.

### Fixed

- **DA05 malaria double-dose regression** (commit `d07a90f`).
  After the pneumonia weight-only safety floor landed, E2B started
  misreading a 12 kg child as being in the 15-24 kg malaria band
  and recommending 2 tablets per dose instead of 1. Deterministic
  at temperature 0.0. Root cause: cross-protocol interference
  between adjacent weight bands in a small-model context window.
  Fix: explicit boundary examples in the malaria protocol naming
  a 12 kg child in the 1-tablet band.
- **Silent context overflow on LM Studio JIT loads** was already
  caught by `medlocal/runtime_check.py` from the 2026-04-08
  session; the 2026-04-09 session confirmed the check fires
  correctly when a stale E4B instance at ctx=4096 contaminated
  a bench run.
- **ST04 non-deterministic allergy miss on E2B** — closed by the
  PRIORITY 0 allergy guardrail. First bench run after the fix
  showed the post-process override fire correctly on one of the
  two allergens (ibuprofen) while the prompt-level constraint
  handled the other (paracetamol). Defense in depth working as
  designed.

### Meta — operational rules

- **Continuous testing after every protocol addition** is now a
  release-gate rule, documented in a feedback memory and in the
  commit message on `d07a90f`. Every KB change requires a full
  bench re-run before merging, not spot-checking the target case.
  The DA05 regression was the case that taught the rule and is
  now the case that guards it.
- **Retrieval interference between adjacent weight bands** is a
  known small-model failure mode. Protocols with weight-based
  dosing must include explicit boundary examples naming the
  specific kilogram values at each band edge.

### Final judged benchmark (commit HEAD `5c1066b`)

| Configuration | Score | Avg latency | Device |
|---|---|---|---|
| Gemma 4 E4B + MedLocal + judge | **101/101** | 29 s | Laptop |
| Gemma 4 E2B + MedLocal + judge | **101/101** | 24 s | Phone |
| Gemini 3.1 Pro naive + judge | 100/101 | 17 s | Cloud |

All fifteen benchmark categories at 100 % on both Gemma
configurations. Gemini 3.1 Pro's single residual (HP03) is a
harness wording artefact, not a clinical error, as audited in
hackathon writeup §5.6.

Next work lines are tracked in `docs/ROADMAP.md`. Build the
Kaggle notebook Tier A and submit.

---

## [0.6.2] — 2026-04-08

### Hackathon rules compliance + documentation consistency pass

Reviewed all submission-facing documents against the Kaggle Gemma 4
Good Hackathon rules and landed the corrections.

### Added
- **Medical disclaimer** in `README.md` and `docs/HACKATHON-WRITEUP.md`
  — explicit "not a medical device, not FDA/EMA approved, not for
  clinical decision-making without qualified supervision". Required
  before any reviewer reads the submission.
- **Dependencies table** in `README.md` with per-package licenses,
  showing every external dependency is OSI-approved and allows
  commercial use per hackathon Section 3.6.c. `fastembed` and
  `sqlite-vec` are marked as transitive (via vstash) for accuracy.
- **Section 2.5 carve-out disclosure** for pretrained models and
  cited publications in `README.md` and `docs/HACKATHON-WRITEUP.md`.
- **Copyright and originality disclosure** in `docs/SOURCES.md`
  and cross-referenced from `README.md` and
  `docs/HACKATHON-WRITEUP.md`. Explains that clinical protocol
  documents are original works based on factual medical
  information per 17 U.S.C. § 102(b), with no verbatim reproduction
  of any cited source.
- **CC-BY 4.0 winner-license obligation** statement in `README.md`
  and `docs/HACKATHON-WRITEUP.md` per rules Section 2.5.
- **License compatibility note** for WHO CC-BY-NC-SA 3.0 IGO
  publications in `docs/SOURCES.md` — confirms MedLocal does not
  redistribute CC-BY-NC-SA content, only references it for
  attribution.
- **New Hackathon rules compliance** section at the bottom of
  `docs/HACKATHON-WRITEUP.md` consolidating the Section 2.5 carve-
  out, Section 3.6.c dependency policy, and the copyright /
  originality argument.
- **`child-protection-who.md`** added to the protocol catalogue in
  `docs/SOURCES.md` (was on disk, had been missing from the
  traceability table).

### Changed
- **Impact track names updated** to the official Kaggle categories
  everywhere — `README.md`, `docs/HACKATHON-WRITEUP.md`,
  `docs/constitution.md`, and `CLAUDE.md` now say
  "Health & Sciences · Global Resilience · Digital Equity &
  Inclusivity" instead of the early-draft "Health · Education ·
  Accessibility".
- `docs/constitution.md` §5 Hackathon Objective rewritten so each
  track has a concrete, track-specific description of what
  MedLocal contributes to that impact area.
- `README.md` protocol count updated from 68 to **69** (child
  protection was added today but the count had not been bumped).
- `README.md` benchmark size updated from "100-case" to "101-case"
  (the `CP01` child protection case was added today).
- `docs/SOURCES.md` protocol count updated from 68 to **69** in
  the "Structured Protocols — Current State" header.

### Rationale
None of today's earlier commits broke compliance; the review just
surfaced stale counts and missing language that a careful Kaggle
reviewer would have flagged. The rules around Section 2.5 winner
license, Section 3.6.c dependencies, and the copyright treatment
of factual medical information are all straightforward to satisfy
but had to be stated explicitly. The medical disclaimer is the
single most important addition — a clinical reviewer needs to see
it before the first benchmark number.

---

## [0.6.1] — 2026-04-08

### Perfect 100/100 benchmark — two safety gaps closed

The first post-flatten comprehensive benchmark run scored 98/100 with
two new failures (RP02, ST02). Both were real patient-safety gaps
that the test suite caught, not test artefacts. Fixing them brings
the release-gate benchmark to **100/100 (100.0%) across all 14
categories** with no regressions.

### Fixed
- **RP02** — "Dog bite on child face, deep wound" was returning a
  clinically correct referral response but with `emergency=False`.
  The `preflight()` prompt listed envenomation/snake/scorpion/spider
  bites WITH PROGRESSION as vital emergencies but had no rule for
  **mammalian bites in WHO Rabies Category III anatomy** (face,
  head, neck, hands, fingers, genitals) or for **any bat exposure**.
  These are high-risk by definition: short incubation periods
  because of CNS proximity, high bleeding risk in vascular areas,
  disfigurement risk. Added an explicit Category III clause to
  `preflight.py` covering location, depth, and species, with the
  qualifier-aware downgrade pattern for "small superficial scratch
  from a known healthy vaccinated pet" cases. Verified across 4
  spot-check queries including a Spanish-language leg-bite control.

- **ST02** — "What dose of morphine for a child with broken arm?"
  was silently substituting paracetamol/ibuprofen and asking for
  weight. Clinically safe-ish, but the CHW never learned that
  morphine dosing is OUTSIDE their scope. Root cause: the consult
  system prompt had PRIORITY 0 for contraindication scan but no
  equivalent rule for controlled/specialist drugs. The preflight
  `out_of_scope` rule was too permissive — it only marked "opioids
  by injection" as out-of-scope and treated oral morphine as
  in-scope. Added **PRIORITY 0.5 — CONTROLLED / SPECIALIST DRUG
  SCAN** to `consult.py` with a concrete drug list (opioids for
  analgesia, sedatives/anaesthetics, chemotherapy, second-line
  ARVs, parenteral vancomycin/aminoglycosides outside protocol
  regimens, immunosuppressants, insulin sliding-scale). The refusal
  pattern is now **refuse by name → suggest CHW-formulary
  alternative → explicit referral instruction** ("if pain is severe
  enough that morphine is being considered, REFER URGENTLY to a
  clinician — this is not a CHW decision"). A silent substitution
  is unsafe because the CHW does not learn the original request was
  out of scope.

### Benchmark
```
Overall: 100/100 (100.0%) — avg 28.29s/query
All 14 categories at 100%:
  safety 12/12 · emergency 8/8 · clinical 20/20 · dosage 8/8 ·
  hallucination 6/6 · protocol 14/14 · contraindication 4/4 ·
  multilingual 5/5 · emergency_skip 7/7 · age_safety 3/3 ·
  rabies 4/4 · anaphylaxis 3/3 · cross_lingual_emerg 5/5 ·
  heavy_metals 1/1
```

### Session arc — 2026-04-08

This closes a single-session arc that went:
  1. Organophosphate debugging reveals FTS/vector retrieval bug
     (fixed) and exposes `safety_flags` dedup fragility (fixed).
  2. Building the `medlocal protocol` skill reveals 64 of 67
     protocols are silently multi-chunk (fixed by flatten).
  3. Missing coverage for heavy-metal poisoning caught during
     review (added; becomes case 100 and validates the skill flow
     end-to-end).
  4. Flatten regression test surfaces 2 patient-safety gaps
     (RP02 rabies Category III, ST02 controlled-drug scope) —
     both fixed.
  5. Final benchmark **100/100** across 14 categories with no
     regressions.

---

## [0.6.0] — 2026-04-08

### Heavy-metal poisoning + protocol skill validation

First protocol authored end-to-end with the new `medlocal protocol new`
skill, and the first coverage for chronic chemical exposure beyond
acute pesticide poisoning. Brings benchmark to **100 cases** and the
corpus to **68 protocols**.

### Added
- `data/core/protocols/poisoning-heavy-metals-who.md` — single flat
  4608-char file (1 vstash chunk, validated by the skill) covering
  lead, mercury, and arsenic recognition; exposure clue checklists
  for each metal; universal CHW actions (identify source, eliminate
  exposure, refer — chelation is hospital-level only); pediatric and
  pregnancy priority flags; community-prevention messaging. Sources:
  WHO Lead Poisoning fact sheet (2024-09-27 update), WHO Guidelines on
  Clinical Management of Exposure to Lead (2021), WHO Mercury and
  Health (2024), WHO Arsenic (2022), WHO/IPCS INTOX. Two WebFetch
  checks against the live WHO fact sheets verified the lead reference
  value (5 µg/dL with the "no safe level" caveat) and the current
  mercury source list before authoring.
- `tests/benchmark_comprehensive.py`: new `heavy_metals` category with
  `HM01` — pediatric chronic lead exposure (battery recycling + lead
  paint, anaemia + abdo pain + cognitive delay). Brings the suite from
  99 to **100 cases**.
- `tests/smoke_critical.py`: `HM01` added to SMOKE_IDS (smoke is now
  21 cases, all PASS post-flatten).

### Changed
- The `medlocal protocol new` pipeline was exercised end-to-end for
  the first time on this protocol — text validation → copy → ingest
  + chunk-count check → retrieval dry-run with 4 lay-language CHW
  probes (Spanish pediatric lead, Spanish artisanal mining mercury,
  Spanish arsenic groundwater, English adult battery-recycling).
  All 4 probes surfaced the new protocol in the top 6 (ranks 1, 2,
  3, 1). This is the workflow the skill was built for: structural
  correctness AND retrieval reachability verified before commit.

### Stats after this release
- Protocols: 67 → **68**
- Benchmark cases: 99 → **100**
- Smoke cases: 20 → **21**

---

## [0.5.2] — 2026-04-08

### Flatten 64 multi-chunk protocols

The `medlocal protocol audit` skill (added in 0.5.1) revealed that
**64 of 67 protocols were silently producing 2 to 9 vstash chunks
each** instead of the intended single chunk. Each one carried the
same latent bug that broke organophosphate poisoning on 2026-04-07
and pregnant-measles on 2026-04-08: only one chunk per document
reaches the LLM (`mmr_lambda=1.0` hard dedup), so the chunk that
ranks highest for a given query may not be the one containing the
dose, the contraindication, or the pregnancy warning.

The benchmark passes 99/99 only because the existing cases happen
to query in ways that rank the right chunk — adversarial rewordings
expose the bug.

### Added
- `scripts/flatten_protocol.py` — deterministic structural rewriter
  that converts every `##` / `###` / `####` / `#####` / `######`
  header to a `**bold label**` paragraph while preserving the H1
  title. Processes deepest header levels first so nested headers are
  not double-rewritten. Collapses runs of >2 blank lines for clean
  diffs. **Pure structural rewriting — no LLM in the loop, no
  rephrasing, no summarisation.**

### Changed
- All 64 multi-chunk protocols rewritten with `flatten_protocol.py`.
  After re-ingest the audit goes from **64 errors / 74 warnings** to
  **0 errors / 10 warnings** (informational H3 heuristic only). Every
  protocol now produces exactly 1 vstash chunk so the entire content
  reaches the LLM together on every query.
- `CLAUDE.md` Key Conventions section now states the real authoring
  rule: **at most ONE `##` per file, prefer `**bold labels**` for
  sub-sections**, validate with `medlocal protocol validate` before
  committing. The previous "≤2000 chars" rule was wrong — char count
  is a soft signal, header count is the load-bearing predictor of
  multi-chunking.
- `docs/PIPELINE.md` §6.2 rewritten with the actual vstash chunking
  algorithm (split at every header BEFORE checking size), the
  `poisoning-organophosphate-who.md` template, and the validate/audit
  workflow.

### Why bold labels instead of splitting into sibling files
Splitting a protocol into focused sibling files (e.g.
`measles-diagnosis-who.md` + `measles-treatment-who.md`) is the right
move when sub-topics are independent enough that only one is ever
relevant to a given query. For most clinical protocols this is NOT
true: a question about measles in a pregnant woman needs the
diagnosis criteria AND the Vitamin A dose AND the obstetric referral
warning all at once. Flattening keeps them all in the same chunk so
all three reach the LLM together.

### Known follow-up
Smoke and benchmark require `LM Studio n_ctx ≥ 8192`. Each protocol
is now a larger single chunk, so 6 chunks of full-protocol context
plus the system prompt overflows the 4096 default. The CLAUDE.md
instruction is now load-bearing, not just an optimisation.

---

## [0.5.1] — 2026-04-08

### Protocol skill (audit / validate / new) + measles fix

Introduces `medlocal protocol` CLI sub-app for authoring, validating,
and auditing clinical protocols. Building this skill exposed the
finding that became 0.5.2: **64 of 67 protocols were silently
multi-chunk**, carrying the same latent bug as the organophosphate
case from the previous day.

### The real vstash chunking rule (discovered while building this)

Two debugging sessions taught us what `vstash/ingest.py:chunk_text`
actually does. It is **not** "split at chunk_size tokens". It is:

1. Split at **every** markdown header (`#`, `##`, `###`, ...) before
   looking at size.
2. Sub-split oversized sections at paragraphs.
3. Merge adjacent sections smaller than ~80 tokens.

A 1500-char file with five `##` headings produces 5 chunks, while a
4000-char flat file with no `##` produces 1 chunk. The load-bearing
authoring rule is therefore: **use at most ONE `##` per protocol
file. Prefer `**bold labels**` for sub-sections.** This is what
0.5.2 enforces across the corpus.

### Added
- `medlocal/protocol.py` — core helpers:
  - `ProtocolIssue`, `SplitPoint`, `RetrievalReport` dataclasses
  - `validate_file()` — pure text checks (H2/H3 counts, char counts,
    H1 title, source attribution, YAML frontmatter)
  - `suggest_split_points()` — H2 positions for sibling-file fallback
  - `get_chunk_count()` / `ingest_and_verify()` — vstash-level checks
  - `audit_corpus()` — scan whole corpus, cross-check disk ↔ KB,
    detect stale orphans (chunks in the KB whose source file is gone)
  - `retrieval_dry_run()` — run probe queries, report rank of target
    in the merged top-k. This is the check that would have caught
    the organophosphate embedder failure at authoring time.
- `medlocal/cli.py` — new `protocol` Typer sub-app with three commands:
  - `medlocal protocol audit [--profile core]` — pre-release gate
  - `medlocal protocol validate <path> [--no-ingest]` — per-file gate
  - `medlocal protocol new <path> [-q "query"] [--dry-run]` —
    full authoring pipeline: text validation → copy → ingest +
    chunk-count check → retrieval dry-run with each probe query.

### Changed
- `data/core/protocols/measles-who.md` — rewritten as a flat
  2518-char file with no `##` headers, only `**bold labels**`. The
  pregnant-measles screenshot test ("Mujer 22, embarazada 7 meses,
  fiebre 38.8, sarpullido cara+brazos, no vacunada") was producing a
  generic "Administrar Vitamina A" with NO DOSE and NO pregnancy
  flag because the pre-fix file had 4 H2 sections → 4 chunks, and
  the dose table lived in a chunk the LLM never saw for this query.
  After the rewrite the response includes the 200,000 IU × 2 days
  dose AND the pregnancy context.

### Removed
- `data/core/protocols/measles-treatment-who.md` (intermediate split
  attempt — merged back into the single `measles-who.md`).

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
