"""Classify on-device benchmark fails as parser vs content bugs.

Reads a bench jsonl emitted by the Kotlin BenchmarkRunner and for every
case simulates the two render-time transforms the APK runs on the raw
LLM answer:

  1. ResponseFormatter.format()  ->  markdown with sections
  2. ParsedConsult.from(md)      ->  (condition, assessment, actions[],
                                      referIf[], source)

Then it matches the must_contain / must_not_contain expectations from
the jsonl line against both the raw answer and each parsed section and
emits a verdict for every fail:

  pass         -> scorer already considered this a pass
  empty        -> raw answer is blank or <20 chars (crash / EOS never
                   fired / cancelProcess killed generation too early)
  truncation   -> raw answer has no SOURCE: line and ends mid-token
  parser       -> raw contains the required keyword but the parsed
                   sections lose it (eg "2" standalone action, empty
                   REFER IF bucket after a typo like REFERELY)
  content      -> raw is well-formed but does not carry the keyword
                   that the scorer expects (actual model-quality gap)

The goal is narrow: before the 2026-04-23 submit we want to know how
many of the 20/101 fails are cheap parser fixes vs how many need a
model prompt rework we cannot fit in three days.

Usage:
    python tests/analyze_android_parser.py tests/bench_android_v3.jsonl
    python tests/analyze_android_parser.py tests/bench_android_v3.jsonl --show-raw
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from benchmark_comprehensive import _check_absent, _check_patterns


# ---------------------------------------------------------------------------
# Python port of Android ResponseFormatter.kt (format + normaliseKey +
# renderList). Kept deliberately literal so a bug in the analyzer is a bug
# in the live renderer too.
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(
    r"^\s*\*{0,2}\s*(CONDITION|CONDICION|CONDICIO\u0301N|DIAGN\u00d3STICO|DIAGNOSTICO|"
    r"ASSESSMENT|EVALUACI\u00d3N|EVALUACION|VALORACI\u00d3N|VALORACION|"
    r"ACTIONS|ACCIONES|REFER[\u00c0-\u024f A-Za-z]*|REFERIR[\u00c0-\u024f A-Za-z]*|"
    r"SOURCE|FUENTE|PROTOCOLO)\s*\*{0,2}\s*:\s*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)

_EMERGENCY_HINTS = (
    "\u26a0",
    "URGENT",
    "URGENTE",
    "URGENTEMENT",
    "REFER IMMEDIATELY",
    "REFERIR IMMEDIATELY",
    "REFERIR INMEDIATAMENTE",
    "REFERER IMM\u00c9DIATEMENT",
)


def _normalise_key(raw: str) -> str:
    u = raw.strip().upper()
    if "CONDI" in u or "DIAGN" in u:
        return "CONDITION"
    if "ASSESS" in u or "EVAL" in u or "VALOR" in u:
        return "ASSESSMENT"
    if "ACTION" in u or "ACCION" in u:
        return "ACTIONS"
    if "REFER" in u:
        return "REFER_IF"
    if "SOURCE" in u or "FUENTE" in u or "PROTOCOLO" in u:
        return "SOURCE"
    return u


def _render_list(body: str, ordered: bool) -> str:
    cleaned = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^\s*\d+[.)]\s*", "", line)
        line = re.sub(r"^[*\-\u2022]\s*", "", line).strip()
        if line:
            cleaned.append(line)
    if ordered:
        return "\n".join(f"{i + 1}. {item}" for i, item in enumerate(cleaned))
    return "\n".join(f"- {item}" for item in cleaned)


def format_response(raw: str) -> str:
    trimmed = raw.strip()
    if not trimmed:
        return raw
    if not _SECTION_RE.search(trimmed):
        return raw

    sections: dict[str, list[str]] = {}
    preamble: list[str] = []
    current_key: str | None = None

    for raw_line in trimmed.splitlines():
        line = raw_line.rstrip()
        match = _SECTION_RE.match(line.lstrip())
        if match:
            current_key = _normalise_key(match.group(1))
            bucket = sections.setdefault(current_key, [])
            inline = match.group(2).strip()
            if inline:
                bucket.append(inline)
        elif current_key is None:
            if line.strip():
                preamble.append(line.strip())
        else:
            sections[current_key].append(line)

    preamble_text = "\n".join(preamble).strip()
    is_emergency = any(h.lower() in preamble_text.lower() for h in _EMERGENCY_HINTS) or any(
        h.lower() in " ".join(sections.get("CONDITION", [])).lower() for h in _EMERGENCY_HINTS
    )

    out: list[str] = []
    if is_emergency:
        out.append("> \u26a0 **URGENT \u2014 REFER IMMEDIATELY**\n\n")
    elif preamble_text:
        out.append(preamble_text + "\n\n")

    for key, content in sections.items():
        body = "\n".join(content).strip().strip("\u2014-").strip()
        if not body:
            continue
        if key == "CONDITION":
            out.append(f"## {body}\n\n")
        elif key == "ASSESSMENT":
            out.append(f"_{body.replace(chr(10), ' ')}_\n\n")
        elif key == "ACTIONS":
            out.append("### What to do\n\n")
            out.append(_render_list(body, ordered=True) + "\n\n")
        elif key == "REFER_IF":
            out.append("### \u26a0 Refer immediately if\n\n")
            out.append(_render_list(body, ordered=False) + "\n\n")
        elif key == "SOURCE":
            out.append("---\n\n")
            out.append(f"_Source: {body}_\n")
        else:
            out.append(f"**{key}**\n\n{body}\n\n")

    return "".join(out).strip()


# ---------------------------------------------------------------------------
# Python port of Android MedLocalConsultCard.kt ParsedConsult.from().
# ---------------------------------------------------------------------------

_H2 = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_H3 = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_HR = re.compile(r"^---\s*$", re.MULTILINE)
_ORDERED_ITEM = re.compile(r"^\d+[.)]\s+(.*)$")


@dataclass
class ParsedConsult:
    emergency: bool = False
    condition: str = ""
    assessment: str = ""
    actions: list[str] = field(default_factory=list)
    refer_if: list[str] = field(default_factory=list)
    source: str = ""

    @classmethod
    def from_markdown(cls, md: str) -> "ParsedConsult":
        text = md.strip()
        emergency = ("\u26a0" in text) and ("urgent" in text.lower())

        body_lines = list(text.splitlines())
        while body_lines:
            t = body_lines[0].strip()
            if t.startswith(">") or t.startswith("\u26a0") or t == "":
                body_lines.pop(0)
            else:
                break
        body = "\n".join(body_lines)

        h2_match = _H2.search(body)
        condition = h2_match.group(1).strip() if h2_match else ""

        h3_matches = list(_H3.finditer(body))
        if h3_matches:
            start = (h2_match.end() + 1) if h2_match else 0
            assessment_raw = body[start:h3_matches[0].start()]
        else:
            after = body.split(h2_match.group(0), 1)[-1] if h2_match else ""
            assessment_raw = after

        assessment = " ".join(
            line.strip() for line in assessment_raw.splitlines() if line.strip()
        ).strip().strip("_").strip()

        sections: dict[str, str] = {}
        for i, m in enumerate(h3_matches):
            start = m.end() + 1
            end = h3_matches[i + 1].start() if i + 1 < len(h3_matches) else len(body)
            sections[m.group(1).strip().upper()] = body[start:end].strip()

        actions_block = ""
        for k, v in sections.items():
            if "WHAT TO DO" in k or "ACTION" in k:
                actions_block = v
                break
        actions: list[str] = []
        for line in actions_block.splitlines():
            line = line.strip()
            if not line:
                continue
            m = _ORDERED_ITEM.match(line)
            if m:
                item = m.group(1).strip()
                if item:
                    actions.append(item)

        refer_block = ""
        for k, v in sections.items():
            if "REFER" in k:
                refer_block = v
                break
        refer_if = []
        for line in refer_block.splitlines():
            line = line.strip()
            if not line:
                continue
            line = line.lstrip("-*\u2022").strip()
            if line and line.lower() != "no se debe referir":
                refer_if.append(line)

        source = ""
        hr = _HR.search(body)
        if hr:
            tail = body[hr.end():].strip()
            tail = tail.removeprefix("_Source:").removesuffix("_")
            tail = tail.removeprefix("Source:").strip()
            source = tail

        return cls(emergency, condition, assessment, actions, refer_if, source)


# ---------------------------------------------------------------------------
# Scoring (mirrors tests/score_android_bench.py)
# ---------------------------------------------------------------------------


def _score_entry(entry: dict) -> tuple[bool, list[str]]:
    cat = entry.get("category", "?")
    text = entry.get("answer", "")
    pf = entry.get("preflight_terms")
    if isinstance(pf, list):
        text = text + "\n" + " ".join(pf)

    if cat == "hallucination":
        out_of_scope = entry.get("preflight_out_of_scope", False)
        scope_hit = _check_patterns(
            text, ["scope|outside|not covered|refer|specialist|hospital|beyond"]
        )
        forbidden_hit = (
            "must_not_contain" in entry
            and not _check_absent(text, entry["must_not_contain"])
        )
        ok = (out_of_scope or scope_hit) and not forbidden_hit
        return ok, [] if ok else ["hallucination probe failed"]

    reasons: list[str] = []
    if entry.get("must_contain") and not _check_patterns(text, entry["must_contain"]):
        reasons.append(f"missing {entry['must_contain']}")
    if entry.get("must_not_contain") and not _check_absent(text, entry["must_not_contain"]):
        reasons.append(f"forbidden {entry['must_not_contain']}")
    if "check_emergency" in entry and entry.get("emergency") != entry["check_emergency"]:
        reasons.append(f"emergency={entry.get('emergency')} exp={entry['check_emergency']}")
    return (not reasons), reasons


# ---------------------------------------------------------------------------
# Verdict classification
# ---------------------------------------------------------------------------


@dataclass
class Verdict:
    bucket: str
    evidence: str


def _keyword_tokens(patterns: list[str]) -> list[str]:
    tokens: list[str] = []
    for pat in patterns:
        for alt in pat.split("|"):
            tokens.append(alt.strip())
    return [t for t in tokens if t]


def _matches_any(text: str, tokens: list[str]) -> list[str]:
    hits: list[str] = []
    low = text.lower()
    for t in tokens:
        if t and t.lower() in low:
            hits.append(t)
    return hits


def classify_fail(entry: dict, reasons: list[str]) -> Verdict:
    raw = entry.get("answer", "") or ""
    raw_stripped = raw.strip()

    if len(raw_stripped) < 20:
        return Verdict("empty", f"raw={len(raw_stripped)} chars")

    formatted = format_response(raw)
    parsed = ParsedConsult.from_markdown(formatted)

    want_emergency = entry.get("check_emergency") is True and entry.get("emergency") is False
    missing_patterns: list[str] = []
    for reason in reasons:
        if reason.startswith("missing "):
            literal = reason[len("missing "):]
            try:
                parsed_patterns = json.loads(literal.replace("'", '"'))
                if isinstance(parsed_patterns, list):
                    missing_patterns.extend(parsed_patterns)
            except json.JSONDecodeError:
                pass

    if want_emergency and not missing_patterns:
        has_refer_markers = any(
            token in raw.lower()
            for token in ("refer", "referir", "urgent", "inmediat", "immediately", "hospital")
        )
        if has_refer_markers:
            return Verdict(
                "parser",
                "emergency-worthy language present in raw but emergency=False (ConsultPipeline.lastEmergency didn't flip)",
            )
        return Verdict(
            "content",
            "no emergency markers in raw - model didn't produce refer/urgent language",
        )

    has_source_line = bool(re.search(r"(?mi)^\s*SOURCE\s*:", raw))
    tail = raw_stripped[-80:]
    looks_truncated = (
        not has_source_line and not tail.endswith((".", "!", "?", ":", "_")) and len(tail.split()) > 0
    )
    if looks_truncated:
        return Verdict("truncation", f"no SOURCE: and tail='{tail[-40:]!r}'")

    tokens = _keyword_tokens(missing_patterns)
    raw_hits = _matches_any(raw, tokens)
    parsed_text = " ".join(
        [
            parsed.condition,
            parsed.assessment,
            " ".join(parsed.actions),
            " ".join(parsed.refer_if),
            parsed.source,
        ]
    )
    parsed_hits = _matches_any(parsed_text, tokens)

    if raw_hits and not parsed_hits:
        return Verdict(
            "parser",
            f"raw matches {raw_hits} but parsed sections lose them (section bucketing drops the content)",
        )

    has_malformed_action = any(
        a == "" or re.fullmatch(r"\d+", a.strip()) is not None for a in parsed.actions
    )
    if has_malformed_action:
        return Verdict(
            "parser",
            f"parsed.actions has a malformed bare-number item: {parsed.actions}",
        )

    if tokens and not raw_hits:
        return Verdict("content", f"raw lacks any of {tokens[:6]}{'...' if len(tokens) > 6 else ''}")

    return Verdict("content", "no parser red flag and raw lacks expected markers")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Print the raw + formatted + parsed view for each fail.",
    )
    parser.add_argument(
        "--only",
        help="Comma-separated list of case IDs to analyze.",
    )
    args = parser.parse_args()

    if not args.jsonl.exists():
        print(f"not found: {args.jsonl}", file=sys.stderr)
        return 2

    only: set[str] | None = None
    if args.only:
        only = {s.strip() for s in args.only.split(",") if s.strip()}

    entries: list[dict] = []
    for line in args.jsonl.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if only and entry.get("id") not in only:
            continue
        entries.append(entry)

    if not entries:
        print("no entries matched filter", file=sys.stderr)
        return 2

    verdicts: dict[str, Verdict] = {}
    bucket_counts: Counter[str] = Counter()
    per_cat_buckets: dict[str, Counter[str]] = defaultdict(Counter)

    fails: list[tuple[dict, list[str]]] = []
    for entry in entries:
        ok, reasons = _score_entry(entry)
        if ok:
            continue
        fails.append((entry, reasons))
        v = classify_fail(entry, reasons)
        verdicts[entry["id"]] = v
        bucket_counts[v.bucket] += 1
        per_cat_buckets[entry.get("category", "?")][v.bucket] += 1

    print(f"Analyzed {len(entries)} entries, {len(fails)} fails.")
    print()
    print("Bucket breakdown:")
    for bucket in ("empty", "truncation", "parser", "content"):
        print(f"  {bucket:<12} {bucket_counts[bucket]:>3}")
    print()
    print(f"{'id':<6}  {'category':<18}  {'bucket':<12}  evidence")
    print("-" * 100)
    for entry, reasons in fails:
        v = verdicts[entry["id"]]
        print(f"{entry['id']:<6}  {entry.get('category', '?'):<18}  {v.bucket:<12}  {v.evidence}")

    if args.show_raw:
        print()
        print("=" * 100)
        for entry, reasons in fails:
            v = verdicts[entry["id"]]
            raw = entry.get("answer", "")
            formatted = format_response(raw)
            parsed = ParsedConsult.from_markdown(formatted)
            print(f"\n### {entry['id']}  ({entry.get('category', '?')})  -> {v.bucket}")
            print(f"Q: {entry.get('q', '')}")
            print(f"Reasons: {reasons}")
            print(f"-- RAW ({len(raw)} chars) --")
            print(raw if raw else "<empty>")
            print("-- PARSED --")
            print(f"  condition: {parsed.condition!r}")
            print(f"  assessment: {parsed.assessment[:200]!r}")
            print(f"  actions:    {parsed.actions}")
            print(f"  refer_if:   {parsed.refer_if}")
            print(f"  source:     {parsed.source!r}")

    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
