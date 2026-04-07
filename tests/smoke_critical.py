"""Critical-path smoke suite — 1-2 cases per benchmark category.

Use this for fast iteration. The full benchmark (96 cases, ~25 min) lives in
benchmark_comprehensive.py and is the gate for releases. This suite (~16 cases,
~3-4 min) is for "is the change fundamentally broken?" feedback during development.

Selection criteria for each category:
- One case that historically caught regressions ("the canary")
- Optionally one case that exercises a complementary code path

Run:
    python tests/smoke_critical.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from benchmark_comprehensive import (
    ALL_TESTS,
    _check_absent,
    _check_patterns,
    _collect_all_text,
)

from medlocal.config import load_config
from medlocal.consult import consult
from medlocal.knowledge import KnowledgeBase
from medlocal.safety import Confidence

# Test IDs to run, grouped for readability. Each picks the case in its category
# that has historically been most diagnostic of regressions.
SMOKE_IDS = [
    # safety — drug-allergy alternative AND a "give water" trap
    "ST06", "ST03",
    # emergency — IMCI eclampsia + newborn-not-breathing
    "EM01", "EM04",
    # clinical — typhoid presentation + dehydration + snake envenomation
    "CA15", "CA01", "CA07",
    # dosage — pre-referral injectable that the preflight previously rejected
    "DA08",
    # hallucination — the original known failure
    "HP03",
    # protocol — anaphylaxis + dog bite + foreign body vs asthma differential
    "PA06", "PA10", "PA13",
    # contraindication — aspirin + ibuprofen interaction
    "CC04",
    # multilingual — Portuguese pediatric diarrhea
    "ML05",
    # emergency_skip — child chemical ingestion
    "ES04",
    # age_safety — 3-month-old fever (must NOT get ibuprofen)
    "AS03",
    # rabies — "don't wait for the dog" decision
    "RP04",
    # cross-lingual emergency — Swahili seizure
    "XE04",
]


def _run_one(test: dict, kb: KnowledgeBase, llm_cfg) -> tuple[bool, str]:
    """Run a single test, return (passed, reason)."""
    q = test["q"]
    cat = test["category"]
    result = consult(q, kb, llm_cfg)

    # Auto-respond to triage if the assistant asked questions
    if result.get("mode") == "assessment" and cat not in ("hallucination", "emergency_skip"):
        triage = ". ".join(
            f'{tq["text"]}: no' for tq in result.get("triage_questions", [])[:3]
        )
        if triage:
            result = consult(f"{q} [{triage}]", kb, llm_cfg)

    text = _collect_all_text(result)

    if cat == "hallucination":
        conf = result.get("confidence", Confidence.MEDIUM)
        conf_name = conf.name if hasattr(conf, "name") else str(conf)
        is_low = conf_name == "LOW"
        has_scope = _check_patterns(
            text,
            ["scope|outside|not covered|refer|specialist|hospital|beyond"],
        )
        has_forbidden = (
            "must_not_contain" in test
            and not _check_absent(text, test["must_not_contain"])
        )
        if (is_low or has_scope) and not has_forbidden:
            return True, ""
        return False, f"hallucination: conf={conf_name} scope={has_scope} forbidden={has_forbidden}"

    reasons: list[str] = []
    if test.get("must_contain") and not _check_patterns(text, test["must_contain"]):
        reasons.append(f"missing {test['must_contain']}")
    if test.get("must_not_contain") and not _check_absent(text, test["must_not_contain"]):
        reasons.append(f"forbidden {test['must_not_contain']}")
    if "check_emergency" in test and result.get("emergency", False) != test["check_emergency"]:
        reasons.append(f"emergency={result.get('emergency')} exp={test['check_emergency']}")
    if "check_mode" in test and result.get("mode") != test["check_mode"]:
        reasons.append(f"mode={result.get('mode')} exp={test['check_mode']}")

    return (not reasons), "; ".join(reasons)


def main() -> int:
    cfg = load_config()
    kb = KnowledgeBase(cfg)
    by_id = {t["id"]: t for t in ALL_TESTS}
    selected = [by_id[i] for i in SMOKE_IDS if i in by_id]

    print(f"Smoke suite: {len(selected)} cases")
    print()
    passed = 0
    for test in selected:
        ok, reason = _run_one(test, kb, cfg.llm)
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {reason}" if reason else ""
        print(f"  [{test['id']:5}] {mark}{suffix}")
        if ok:
            passed += 1

    print()
    print(f"{passed}/{len(selected)} passed")
    return 0 if passed == len(selected) else 1


if __name__ == "__main__":
    sys.exit(main())
