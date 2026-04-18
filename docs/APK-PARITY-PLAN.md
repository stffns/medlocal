# MedLocal APK - Parity Plan

> Plan to close the on-device gap from **81/101 (80%)** on Gemma 4 E2B
> against the Python baseline of **101/101**. For a medical application
> 80% is not acceptable. This document is the entry point for the next
> work session.
>
> Authored 2026-04-18 after three back-to-back on-device bench runs
> (v1 87/101 with runaways inflating the score, v2 80/101 with 90 s
> timeout, v3 80/101 with 150 s timeout). The v2/v3 agreement confirms
> that 80 % is the honest baseline and that the gap is structural,
> not noise.

---

## Root cause of the gap

Python reaches 101/101 because it uses `chat_structured()` with a
JSON schema enforced at the llama.cpp sampler level. Grammar-
constrained decoding:

- Forces the model to fill `{mode, urgency, condition, assessment,
  actions[], refer_if[], source, answer}`.
- Stops generation cleanly when the JSON object closes.
- Makes runaway generation structurally impossible.

LiteRT-LM does not have a `response_format` parameter. Without it,
Gemma 4 E2B produces free text and on ~8 cases per run loops until
context is exhausted (the "monitor, monitor, monitor..." pattern we
saw on ST03 with 22 KB of output in 285 s). This is the one
structural difference between the two pipelines. Everything else is
already ported.

---

## Task plan (priority order)

### P0 - Stream + EOS termination (ceiling +5 to +8 cases)

Replace `instance.conversation.sendMessage(Contents)` with
`instance.conversation.sendMessageAsync(Contents): Flow<Message>` in
`BenchmarkRunner.kt` and the chat VM. Accumulate streamed tokens
into a `StringBuilder`; on each token emission check for an EOS
marker (the `SOURCE:` line followed by a newline, or two consecutive
newlines at end of buffer). When detected, call
`instance.conversation.cancelProcess()` and return the accumulator.

Side benefits:
- Partial output on the 8 runaway cases becomes available for
  scoring instead of being discarded via `CANCELLED` exception.
- Naturally caps output length without a hard timeout.
- Matches Python's early-stop-on-schema-close behaviour.

Risk: the cancel may produce a `CANCELLED` exception in the Flow.
Catch it, return whatever the accumulator has.

### P1 - Port the full Python safety pattern tables (ceiling +4 to +6 cases)

The Kotlin `Safety.kt` has:
- **Emergency patterns**: ~25 regexes (Python has ~50+).
- **Allergy drug aliases**: 8 drugs (Python has 13).
- **Controlled drug categories**: 5 (Python has 13).

Specific missing coverage that the 2026-04-17 v3 bench surfaced:

| ID | Why it fails on Kotlin |
|---|---|
| ES02 | head trauma + confusion + vomiting; no regex for TBI signs |
| ES04 | chemical ingestion in Spanish ("limpieza", "limpiador") - Kotlin only matches `bleach|kerosene|pesticide|acid|caustic` |
| ES06 | overdose phrasing "took 20 tablets" - Kotlin matches `overdose` only |
| RP02 | dog bite deep wound - no regex for bite + bleeding combos |
| XE04 | Swahili danger signs (`degedege` = convulsions, `hawezi kunywa` = unable to drink) - Kotlin only English + Spanish |
| CP01 | child abuse markers (`moretones múltiples`, `patrones`, behavioural red flags) - no CP regex family |

Allergy aliases to add:
- `valproate`, `metformin`, `enalapril` (ACEi family),
  `warfarin`, `losartan` (ARB family), plus their class bridges.

Controlled drug categories to add:
- Non-opioid controlled analgesics, tricyclic antidepressants,
  MAOIs, lithium, warfarin (as needs monitoring), insulin
  sliding-scale, second-line TB drugs.

Cross-reference `medlocal/safety.py` verbatim line-by-line. The port
is mechanical once the tables are identified.

### P2 - Force conciseness in the prompt (ceiling +2 to +4 cases)

Two changes to `ConsultPipeline.kt`:

1. Append an explicit stop rule to `FORMAT_INSTRUCTION` and
   `FORMAT_GUIDANCE_ONLY`:

   ```
   Write the SOURCE: line as the LAST line of your response.
   Do not write anything after the SOURCE: line.
   Maximum 12 lines of total output.
   ```

2. Inject 2-3 few-shot example answers in `SYSTEM_PROMPT` to anchor
   the target length and format. Pick:
   - A contraindication refusal (aspirin + Reye pattern).
   - A standard guidance case (diarrhoea with ORS).
   - An emergency referral (eclampsia).

   Each example ≤ 8 lines. This primes E2B to match the target
   shape instead of drifting into protocol regurgitation.

### P3 - Validate Gemma 4 E4B as the deployment target

E2B was the original choice for phone-class memory. But on the
S24 Ultra with 11 GB RAM, E4B runs comfortably and produces better
clinical answers. Hypothesis: E4B with the same pipeline hits 95 %+.

Steps:
1. Download E4B in the app model picker (already wired).
2. Run the same 101-case bench against E4B.
3. Compare scores.
4. If E4B clears 95 %, update the writeup story to
   *"E4B recommended, E2B fallback for memory-constrained devices"*.

This is an honest re-framing: MedLocal ships the strongest on-device
model the hardware supports, with E2B as the graceful degradation
path.

### P4 - Preflight prompt reconciliation

The 2026-04-17 v3 fails show `emergency=False` where Python would
return `True` (ES02, ES04, ES06, RP02, XE04, CP01). Six cases where
the LLM-based emergency classification differs between stacks.

The Kotlin `Preflight.SYSTEM_PROMPT` was condensed from the Python
`preflight.py` to fit inline. Condensation likely dropped nuance
that the classifier relies on. Two options:

- Copy Python's preflight prompt verbatim and measure.
- Add explicit few-shot cases for the six failure modes above.

This overlaps with P1 (regex safety-net also catches these). If P1
lands and closes the 6-case gap regex-side, P4 becomes optional.

---

## What is already correct (do not touch)

- 9-layer pipeline ported to Kotlin (`ConsultPipeline.kt`,
  `Safety.kt`, `Preflight.kt`, `AuditLog.kt`, `StructuredOutput.kt`,
  `AnswerCleaner.kt`, `KeywordExpander.kt`, `LlmHelpers.kt`,
  `ProtocolSearch.kt`).
- 4-pass FTS5 retrieval matching Python (raw + preflight AND/OR
  + static keywords + BM25 safety-net).
- AnswerCleaner handling LaTeX and protocol-ref stripping (port of
  Python `_clean_protocol_refs`).
- FORMAT_INSTRUCTION reformed to remove the bracket placeholders
  that E2B was echoing verbatim.
- Dedicated short out-of-scope refusal prompt.
- 150 s per-case timeout with `Conversation.cancelProcess()`.
- Bench harness on-device (`BenchmarkRunner`, `BenchmarkDialog`).
- Python judge (`tests/score_android_bench.py`) reads the jsonl
  directly and scores by category.
- `applicationId = com.medlocal.android` so the fork coexists with
  Google's Edge Gallery sample.
- Python laptop bench still 101/101 with MLX Gemma 4 E4B.

---

## Bench commits on `feat/medlocal-spike`

```
fe42682  wip safety wiring preservation
e02d577  BenchmarkRunner + Dialog + 101 case assets
f7eff1b  trigger hook inside LlmChatTaskModule
fcaac5e  applicationId -> com.medlocal.android
9ef13d0  AnswerCleaner + de-bracket FORMAT instruction
8dc858a  Android ICU regex fixes (unpaired } and ])
329e5a9  90 s per-case timeout via cancelProcess
1f4fdca  out-of-scope dedicated short refusal
4387342  150 s per-case timeout
```

Python side on `main`:
```
3e802cc  feat(bench): android case exporter + score script
```

---

## Snapshot for the new session

- Current score: **81 / 101 (80 %)** on Gemma 4 E2B, S24 Ultra.
- Bench runtime: ~60-65 min per run on S24 Ultra.
- Raw artefact to pull and score:
  ```
  adb pull /sdcard/Android/data/com.medlocal.android/files/bench_results.jsonl tests/bench_android.jsonl
  python tests/score_android_bench.py tests/bench_android.jsonl
  ```
- Laptop reference: MLX Gemma 4 E4B + smoke still 22/22.
- Target realistic after P0+P1+P2: **90-95 / 101**.
- Target ambitious with P3 (E4B deployment): **98+ / 101**.
- Path to full 101 / 101 parity without touching LiteRT-LM upstream
  probably needs stream+EOS + E4B + fine prompt iteration. 2-3
  further sessions.

---

## How to pick up

1. Read this doc and `docs/PIPELINE.md` for pipeline internals.
2. Checkout `feat/medlocal-spike` in
   `~/Desktop/Personal/Projects/medlocal-android`.
3. Start with **P0 (stream + EOS)** because it both rescues the 8
   runaway cases AND is prerequisite work for any prompt-engineering
   approach (without streaming we cannot cap output by marker).
4. Rebuild, reinstall, rerun bench, score. Iterate.

Success criterion for closing this workstream: **≥ 95 / 101 on-device
with the same 9-layer safety pipeline, on a device we can hand to
a community health worker.**
