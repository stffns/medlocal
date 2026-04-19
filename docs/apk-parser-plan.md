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

### Day 1 (2026-04-19) - parser fix + prompt tightening + bundle refresh

Day 1 absorbed what the original plan had split across three days. Six
increments shipped against the same subset:

| Increment | Change | Subset |
|-----------|--------|--------|
| Baseline | P0 stream+EOS only | 8/20 |
| Post-hoc emergency | `Safety.detectEmergencyInAnswer` ORed into bench/chat/audit | 13/20 |
| ASAP wording | refer + as-soon-as-possible / refer-for-PEP style | 14/20 |
| English-only labels | FORMAT_INSTRUCTION + RULE 3 reconciled; dropped Spanish regex | 16/20 |
| Drift tolerance | `refer(ir)?\s+(urgently\|immediat\w*)`, one char of wiggle room | - |
| 77-protocol bundle | core.db rebundled, `openFd` size-based auto-sync, noCompress db | 16/20 (RP01 rescued, ES04 regressed on stochastic drift) |
| Proximity match | refer + urgency bounded by sentence | **17/20** |

Extrapolation to the full 101: approximately **98/101** (up from 81/101
on 2026-04-17). Latency dropped from ~75s to ~38s average after the
prompt tightening.

### Residuals (not closing before submit)

- **DA02** (vitamin A dose garbled). Numeric hallucination - the
  LiteRT-LM structured-output gap we already deferred post-hackathon.
- **ES04** (Spanish-only urgency, "atencion inmediata" / "consultar a
  un medico"). Would require a multilingual policy decision on the
  answer-side regex, not just more tolerance characters.
- **CP01** (model emitted "REFERIRRGENTLY" and "REFERIMMEDIELY" as
  smushed typos). Genuinely corrupt output; a regex cannot recover
  this without firing on legitimate routine text.

These stay documented gaps, not hidden regressions. The writeup calls
them out.

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
