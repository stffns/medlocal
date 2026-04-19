# Next session kickoff - 2026-04-20

Picks up from session 2026-04-19 which closed the APK subset at 17/20
(extrapolated ~98/101). Three days left to the 2026-04-23 Kaggle submit.

## State at hand

- Branches: `feat/apk-parser-fixes` on both stffns/medlocal and
  stffns/medlocal-android (fork created mid-session since the upstream
  is google-ai-edge/gallery).
- PRs open and pushed to HEAD:
  - https://github.com/stffns/medlocal/pull/2 (Python: analyzer +
    subset + search_api /search fix + plan doc + 6 jsonl runs)
  - https://github.com/stffns/medlocal-android/pull/1 (Kotlin:
    post-hoc emergency + prompt tightening + English-only regex +
    proximity match + 77-protocol DB + noCompress db)
- APK on device already has the latest commit (418ebb1) installed.
- Subset file still on device at
  `/sdcard/Android/data/com.medlocal.android/files/bench_subset_ids.txt`.

## Tomorrow's first hour - full 101 parity run

The subset number is marketing; the writeup cites the full bench.

```
# remove subset filter so all 101 cases run
adb shell "run-as com.medlocal.android rm files/bench_subset_ids.txt" \
  || adb shell rm /sdcard/Android/data/com.medlocal.android/files/bench_subset_ids.txt

# trigger from the app (BenchmarkDialog). Expect ~60 minutes on E2B
# at ~38s avg latency.

# when it finishes
adb pull /sdcard/Android/data/com.medlocal.android/files/bench_results.jsonl \
  tests/bench_android_full_2026-04-20.jsonl
python tests/score_android_bench.py tests/bench_android_full_2026-04-20.jsonl
python tests/analyze_android_parser.py tests/bench_android_full_2026-04-20.jsonl
```

Sanity check: the category breakdown should look like the 2026-04-17
run but with `emergency_skip`, `rabies`, `child_protection`,
`anaphylaxis`, `clinical` all lifted. If `dosage` still sits at 6/8
that is expected (DA02 is the structured-output residual).

Commit the jsonl as `tests/bench_android_full_2026-04-20.jsonl` under
the same PR. That number is what the writeup quotes.

## Second priority - writeup update

`docs/HACKATHON-WRITEUP.md` still reports the 2026-04-17 APK parity
(81/101). Update with:

- Final number from the full 101 run above.
- Honest residuals: DA02 structured-output gap, ES04 multilingual
  urgency policy decision, CP01 corrupt-output case.
- Note the bundle refresh - the 8 protocols added on device.
- Keep the "structured output gap" framing from `docs/APK-PARITY-PLAN.md`
  so the submission does not overclaim LiteRT-LM capability.

## Third priority - Kaggle upload

Still pending from 2026-04-18 close. Notebook + code + writeup package
goes to Kaggle, final verification runs on Kaggle infra (not device).
APK is optional supporting material; the grading target is the
notebook / Python pipeline.

## Fourth priority - video demo

Recording still pending. Script beats:
1. Question in Spanish -> answer in Spanish, all structural labels in
   English, emergency chip fires.
2. Penicillin-allergy pneumonia (ST06 in the subset) -> model picks
   erythromycin/azithromycin thanks to the Drug Allergies Alternatives
   protocol.
3. Dog bite on leg -> rabies protocol surfaces (RP01 rescue, shows
   the 77-protocol bundle paying off).
4. Offline mode demo (airplane mode).

## Do not touch

- DA02, ES04, CP01 residuals. Any "last-minute fix" on these three
  risks regressing the 17 that pass. They are accepted gaps documented
  in the writeup.
- SYSTEM_PROMPT RULE 3 vs FORMAT_INSTRUCTION. The reconciliation in
  `ea38114` + `5848632` is load-bearing for the English-only labels;
  the 2026-04-19 gemini review flagged a contradiction that we already
  resolved.
- Question-side `EMERGENCY_PATTERNS` regex. Widening it is how we
  regressed DA05 on 2026-04-09. The answer-side scan is the correct
  layer.

## If time permits

- Merge PR #2 and #1 once the full 101 run confirms no regression.
  Both are clean-green so no blockers.
- Clean up the stale `feat/medlocal-spike` branch once PR #1 merges.
- Update `CLAUDE.md` protocol count from "67" to "77" to match reality.
