# APK parser vs content plan (2026-04-19 -> 2026-04-23 submit)

Goal: narrow the on-device parity gap in the three days we have before
the Kaggle submit. This plan is scoped to things that can ship in a
week, not a proper runtime rework (LiteRT-LM grammar enforcement is
still deferred per `docs/APK-PARITY-PLAN.md`).

## Baseline (2026-04-19)

Ran the 20 failing cases from `bench_android_v3.jsonl` (the 2026-04-17
run) against the current APK (`feat/medlocal-spike` + P0 stream+EOS from
`eb6cf69`). Results in `tests/bench_android_subset_2026-04-19.jsonl`.

```
TOTAL        8 /  20   (40%)
```

8 of the 20 cases that failed on v3 now pass - those are the 8 cases
that used to be empty-answer crashes (ST03, CA06, ML03, ES01, AS01,
AS03, AX01, XE03). P0 stream+EOS did its job.

Of the remaining 12 fails, `tests/analyze_android_parser.py` classifies:

| Bucket | Count | Case IDs |
|--------|-------|----------|
| empty | 0 | - |
| truncation | 0 | - |
| parser | 6 | ES02, ES04, ES06, RP02, XE04, CP01 |
| content | 6 | ST06, CA11, DA01, DA02, RP01, RP04 |

All 6 parser fails are the SAME root cause: `ConsultPipeline.lastEmergency`
is computed from preflight + a question-side regex that is English-only
(with a handful of Spanish danger words). The LLM's answer clearly asks
for urgent referral ("REFER URGENTLY", "REFERIR URGENTLY", "REFER
IMMEDIATELY") in all 6, but the emergency chip never turned on.

## Attack plan

### Day 1 (2026-04-19, today) - parser fix: post-hoc emergency detection

**Change** (landed in this commit):

- `medlocal/Safety.kt`: new `detectEmergencyInAnswer(answer)` scans
  the response for `REFER URGENTLY` / `REFER IMMEDIATELY` /
  `REFERIR URGENTLY` / `REFERIR INMEDIATAMENTE` / `URGENT -- REFER` /
  the warning-triangle + URGENT marker.
- `medlocal/BenchmarkRunner.kt`: OR the post-hoc signal into the
  `emergency` field written to the jsonl.
- `ui/llmchat/LlmChatViewModel.kt`: OR the post-hoc signal into the
  MedLocalConsultMeta the consult card reads, and into the audit log.

Rationale: closes the gap at the render boundary without changing
preflight, so there is no risk of regressing the refer/urgent flag on
cases that already pass. The question-side regex stays English-only
on purpose - widening it to cover every language is exactly the kind
of retrieval drift that 2026-04-09 DA05 taught us to avoid.

Expected gain: +6 cases on the subset (8/20 -> 14/20), which maps to
87/101 on the full 101-case bench.

### Day 2 (2026-04-20) - parser polish

Three smaller render-side fixes surfaced in the subset raw output:

1. **Bare-number action** (seen in screenshot, ES04 raw). `ResponseFormatter.renderList`
   regex `^\s*\d+[.)]\s*` does not strip a digit that has no trailing
   punctuation, so `"2"` on its own line survives as an empty action.
   Fix: add `|^\s*\d+\s*$` to the filter so bare digits are dropped.
2. **Leaked chain-of-thought preamble** (DA02 raw starts with
   `PRIORITY 0 -- CONTRAINDICATION SCAN ... STEP 1 ... STEP 3 ...`
   before the CONDITION line). The model echoed the system prompt's
   reasoning scaffold. Either add an explicit stop-before-CONDITION
   rule to the prompt or drop everything before the first SECTION_RE
   match in `ResponseFormatter.format`.
3. **Typo-tolerant REFER header** - the model sometimes emits
   `REFERELY IF`, `REFER IMMEDIAT:`, `REFERATELY`. `SECTION_RE`
   currently catches most of these via `REFER[\p{L} ]*`, but the
   empty-inline variant (no text after colon, bullets on the next
   line) collapses to an empty REFER_IF bucket. Fix: keep the bucket
   even when the inline body is empty.

### Day 3 (2026-04-21) - cheap content fixes

Three of the six content fails look like retrieval/prompt issues, not
model-quality gaps:

- **ST06** (penicillin-allergic child with pneumonia, missed
  erythromycin/azithromycin). The model answered with amoxicillin
  despite the question stating the allergy. ConsultPipeline has
  `extractAllergies` but the allergy is not being surfaced to the
  prompt with enough weight. Try a harder guardrail: prepend
  "Patient is ALLERGIC to penicillin, do NOT recommend any
  beta-lactam" when `lastAllergies` contains penicillin.
- **RP01** (dog bite on leg, retrieved fracture protocol). The
  Spanish word "pierna" dominates the retrieval signal over "perro"
  + "mordio". Add a static trigger in `KeywordExpander.expandStatic`
  that maps `(perro|dog).*(mordio|bit|bite)` to the rabies
  protocol title tokens.
- **RP04** (stray dog bite, model recommended antivenom). The model
  confused rabies PEP with snakebite antivenom. Add a prompt guardrail
  that says "antivenom is for snakebite only - use rabies vaccine or
  immunoglobulin for animal bites". Similar pattern to the existing
  controlled-drug guard.

Leave for post-submit (need a model or prompt rework we cannot fit):

- **CA11** (wheeze without foreign-body findings, retrieved FBA
  protocol instead of asthma). Needs the asthma/FBA disambiguator.
- **DA01, DA02** (amoxicillin + vitamin A dose garbled). Numeric
  hallucinations are the LiteRT-LM grammar-gap symptom. Fix is
  structured output, which we have deferred.

## Verification

After each day's change, re-run the subset on device:

```
adb push tests/bench_android_subset.txt \
  /sdcard/Android/data/com.medlocal.android/files/bench_subset_ids.txt
# trigger bench from app
adb pull /sdcard/Android/data/com.medlocal.android/files/bench_results.jsonl \
  tests/bench_android_subset_YYYY-MM-DD.jsonl
python tests/score_android_bench.py tests/bench_android_subset_YYYY-MM-DD.jsonl
python tests/analyze_android_parser.py tests/bench_android_subset_YYYY-MM-DD.jsonl
```

Before the submit on 2026-04-23, delete
`/sdcard/Android/data/com.medlocal.android/files/bench_subset_ids.txt`
on device and re-run the full 101 to get the final parity number to
cite in the writeup.
