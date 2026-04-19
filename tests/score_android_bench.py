"""Score the Android on-device benchmark jsonl.

Reads bench_results.jsonl produced by the Kotlin BenchmarkRunner and
applies the same pattern checks benchmark_comprehensive.py uses on
Python. Every case line carries its must_contain / must_not_contain
spec inline, so this script does not need to re-load ALL_TESTS.

Regex fast path only - does NOT call the Gemini judge. That was the
decision in the design: quick rejection of obvious fails, the LLM
judge can run later if Jay wants to resolve wording-artefact cases
the same way we did on Python.

Usage:
    python tests/score_android_bench.py tests/bench_android.jsonl

Output: per-category pass/fail + grand total, plus a FAILS list with
the first 120 chars of each failing answer so the regression is
skimmable without re-reading the full jsonl.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from benchmark_comprehensive import _check_absent, _check_patterns


def _collect_text(entry: dict) -> str:
    # The Kotlin runner writes a flat "answer" string (text-header format).
    # Join any extra structured fields the runner surfaces for parity with
    # Python's _collect_all_text - today it only ships answer + preflight.
    bits = [entry.get("answer", "")]
    pf = entry.get("preflight_terms")
    if isinstance(pf, list):
        bits.append(" ".join(pf))
    return "\n".join(bits)


def _score_one(entry: dict) -> tuple[bool, list[str]]:
    cat = entry.get("category", "?")
    text = _collect_text(entry)

    # Hallucination probes: pass if preflight flagged out-of-scope OR the
    # answer mentions scope/refer, AND does not include a forbidden token.
    if cat == "hallucination":
        out_of_scope = entry.get("preflight_out_of_scope", False)
        scope_hit = _check_patterns(
            text,
            ["scope|outside|not covered|refer|specialist|hospital|beyond"],
        )
        forbidden_hit = (
            "must_not_contain" in entry
            and not _check_absent(text, entry["must_not_contain"])
        )
        ok = (out_of_scope or scope_hit) and not forbidden_hit
        reason = (
            ""
            if ok
            else f"out_of_scope={out_of_scope} scope={scope_hit} forbidden={forbidden_hit}"
        )
        return ok, [reason] if reason else []

    reasons: list[str] = []
    if entry.get("must_contain") and not _check_patterns(text, entry["must_contain"]):
        reasons.append(f"missing {entry['must_contain']}")
    if entry.get("must_not_contain") and not _check_absent(text, entry["must_not_contain"]):
        reasons.append(f"forbidden {entry['must_not_contain']}")
    if "check_emergency" in entry and entry.get("emergency") != entry["check_emergency"]:
        reasons.append(f"emergency={entry.get('emergency')} exp={entry['check_emergency']}")
    if "check_mode" in entry:
        # mode is not captured in the text-header jsonl today - skip the
        # assertion rather than false-fail every such case. Left here for
        # when the Kotlin runner starts emitting a mode field.
        pass
    return (not reasons), reasons


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    parser.add_argument(
        "--show-fails",
        action="store_true",
        help="Print full answers for failing cases (useful for diagnosis).",
    )
    args = parser.parse_args()

    if not args.jsonl.exists():
        print(f"not found: {args.jsonl}", file=sys.stderr)
        return 2

    entries: list[dict] = []
    for line in args.jsonl.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        entries.append(json.loads(line))

    print(f"Loaded {len(entries)} cases from {args.jsonl}")
    print()

    by_cat_total: dict[str, int] = defaultdict(int)
    by_cat_pass: dict[str, int] = defaultdict(int)
    fails: list[tuple[dict, list[str]]] = []
    total_latency = 0

    for e in entries:
        cat = e.get("category", "?")
        ok, reasons = _score_one(e)
        by_cat_total[cat] += 1
        if ok:
            by_cat_pass[cat] += 1
        else:
            fails.append((e, reasons))
        total_latency += int(e.get("latency_ms", 0))

    print(f"{'category':<22} {'pass':>5} / {'total':>5}")
    print("-" * 40)
    for cat in sorted(by_cat_total.keys()):
        p, t = by_cat_pass[cat], by_cat_total[cat]
        pct = (p * 100 // t) if t else 0
        print(f"{cat:<22} {p:>5} / {t:>5}   ({pct}%)")
    print("-" * 40)
    p_total = sum(by_cat_pass.values())
    t_total = sum(by_cat_total.values())
    pct_total = (p_total * 100 // t_total) if t_total else 0
    print(f"{'TOTAL':<22} {p_total:>5} / {t_total:>5}   ({pct_total}%)")
    if t_total:
        print(f"Avg latency: {total_latency // t_total}ms")

    if fails:
        print()
        print(f"FAILS ({len(fails)}):")
        for e, reasons in fails:
            snippet = (e.get("answer") or "").replace("\n", " ")[:120]
            print(f"  [{e.get('id','?'):6}] {e.get('category','?'):<18} - {'; '.join(reasons)}")
            if args.show_fails:
                print(f"      A> {snippet}")

    return 0 if p_total == t_total else 1


if __name__ == "__main__":
    raise SystemExit(main())
