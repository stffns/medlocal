#!/usr/bin/env python
"""Flatten a protocol file by converting H2/H3 headers to bold labels.

Usage:
    python scripts/flatten_protocol.py <path> [--write]

Without --write it prints the flattened output to stdout (dry-run).
With --write it overwrites the file in place.

Rules:
  - H1 (`# ...`) preserved as-is
  - H2 (`## X`) → `**X.**` paragraph (with blank line separators)
  - H3 (`### X`) → `**X:**` paragraph (slightly different form so they
    still read as nested sub-labels to humans)
  - Blank lines around the bold labels preserved for readability
  - Everything else untouched
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

# Match H2 through H6. H1 is preserved as the file title. vstash's chunker
# splits on ANY markdown header level, so we have to flatten all non-H1
# levels or the file will still fragment.
_H6 = re.compile(r"^######\s+(.+?)\s*$", re.MULTILINE)
_H5 = re.compile(r"^#####\s+(.+?)\s*$", re.MULTILINE)
_H4 = re.compile(r"^####\s+(.+?)\s*$", re.MULTILINE)
_H3 = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _label_h2(m: re.Match) -> str:
    title = m.group(1).rstrip(":.").strip()
    return f"**{title}.**"


def _label_h3(m: re.Match) -> str:
    title = m.group(1).rstrip(":.").strip()
    return f"**{title}:**"


def _label_h4(m: re.Match) -> str:
    title = m.group(1).rstrip(":.").strip()
    return f"**{title}:**"


def _label_h5(m: re.Match) -> str:
    title = m.group(1).rstrip(":.").strip()
    return f"_{title}:_"


def _label_h6(m: re.Match) -> str:
    title = m.group(1).rstrip(":.").strip()
    return f"_{title}:_"


def flatten(text: str) -> str:
    # Process deepest levels first so an H4 inside an H2 section is not
    # accidentally rewritten twice.
    text = _H6.sub(_label_h6, text)
    text = _H5.sub(_label_h5, text)
    text = _H4.sub(_label_h4, text)
    text = _H3.sub(_label_h3, text)
    text = _H2.sub(_label_h2, text)
    # Collapse runs of blank lines to max 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def main() -> int:
    args = sys.argv[1:]
    write = "--write" in args
    args = [a for a in args if a != "--write"]
    if not args:
        print(__doc__)
        return 2
    p = Path(args[0])
    if not p.exists():
        print(f"error: {p} does not exist", file=sys.stderr)
        return 1
    original = p.read_text(encoding="utf-8")
    flattened = flatten(original)
    if write:
        p.write_text(flattened, encoding="utf-8")
        print(f"✓ wrote {p} ({len(original)} → {len(flattened)} chars)")
    else:
        sys.stdout.write(flattened)
    return 0


if __name__ == "__main__":
    sys.exit(main())
