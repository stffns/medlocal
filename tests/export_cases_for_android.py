"""Export ALL_TESTS from benchmark_comprehensive.py to a JSON file the
Android bench runner can load from assets.

Usage:
    python tests/export_cases_for_android.py [--out PATH]

Default output:
    ../medlocal-android/Android/src/app/src/main/assets/benchmark_cases.json

Keeps only the fields the Kotlin runner needs. The Python judge reads
the same ALL_TESTS, so Kotlin writes the raw {id, question, answer,
preflight, safety_flags, latency_ms} to bench_results.jsonl and the
Python side matches by id to score.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark_comprehensive import ALL_TESTS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "medlocal-android/Android/src/app/src/main/assets/benchmark_cases.json",
    )
    args = parser.parse_args()

    out: list[dict] = []
    for t in ALL_TESTS:
        entry = {
            "id": t["id"],
            "category": t["category"],
            "q": t["q"],
        }
        # Optional fields - only include when present so the Kotlin side
        # can omit them without guarding every field.
        for k in ("must_contain", "must_not_contain", "check_emergency",
                  "check_mode", "condition"):
            if k in t:
                entry[k] = t[k]
        out.append(entry)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"wrote {len(out)} cases -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
