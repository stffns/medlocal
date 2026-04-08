"""Protocol authoring, validation, and audit.

This module is the single source of truth for "is this protocol file
healthy before it reaches a CHW?". The rules are empirical — they come
from two debugging sessions (poisoning-who.md and measles-who.md on
2026-04-07/08) that revealed the real vstash chunking behaviour:

  THE CRITICAL RULE — **every protocol must produce exactly ONE
  vstash chunk**. When a file splits into several chunks, only the
  highest-scoring one for a given query reaches the LLM, so any
  treatment block or dose table that happens to live in a "losing"
  chunk silently disappears from the answer. Atropine doses, Vitamin
  A doses, contraindication lists — all vulnerable.

  HOW vstash CHUNKS MARKDOWN — this is what we learned the hard way
  by reading vstash/ingest.py:chunk_text(). The chunker:
    1. Splits at **every markdown header** (`#`, `##`, `###`, ...)
       BEFORE looking at size.
    2. Splits oversized sections further by paragraph.
    3. Merges adjacent sections smaller than ~80 tokens.

  THE PRACTICAL RULE for authoring therefore is NOT "≤2000 chars per
  file". It is:

      Use AT MOST ONE `##` header per file. Prefer **bold labels**
      (`**Signs:**`) for sub-sections. Each file stays flat, vstash
      keeps it as one chunk, and the LLM sees the whole protocol at
      once.

  Supporting rules:

  - **Source attribution** — every protocol cites WHO/MSF/Hesperian/
    IMCI/IMAI/CDC/NICE with a year. Double grounding depends on it.
  - **H1 title present** — helps both humans and retrieval titles.
  - **No YAML frontmatter** — vstash treats it as body content and
    it pollutes embeddings.
  - **No stale orphans in the DB** — files deleted from disk whose
    chunks linger in vstash keep beating real protocols on FTS.

Used by `medlocal protocol audit|validate|new` in the CLI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .knowledge import KnowledgeBase

Severity = Literal["error", "warn", "info"]

# Authoring rules
# Char counts are soft signals. The authoritative check is vstash chunk
# count, enforced by ingest_and_verify(). But a 4000-char file with one
# H2 still produces one chunk, while a 1500-char file with five H2s
# produces five. So char count alone is not enough — we also check H2
# header count as a *predictor* of multi-chunking.
SOFT_TARGET_CHARS = 2500  # above this, warn — even with flat structure it's getting risky
WARN_CHARS = 3500  # above this, warn harder — likely to force paragraph-level splits
MAX_H2_SECTIONS = 1  # vstash splits at every ##, so one per file is the safe ceiling

_SOURCE_RE = re.compile(
    r"(?im)^\s*(?:\*\*)?source(?:\*\*)?[:\s]+.*?(WHO|MSF|Hesperian|IMCI|IMAI|CDC|NICE)",
)
_H1_RE = re.compile(r"^#\s+\S+")
_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_YAML_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)


@dataclass
class ProtocolIssue:
    """One rule violation found in a protocol file."""

    path: str
    severity: Severity
    rule: str
    message: str
    fix_hint: str = ""

    def __str__(self) -> str:
        tag = {"error": "✗", "warn": "⚠", "info": "ℹ"}[self.severity]
        name = Path(self.path).name if self.path else "(no path)"
        out = f"{tag} [{self.rule}] {name}: {self.message}"
        if self.fix_hint:
            out += f"\n  → {self.fix_hint}"
        return out


@dataclass
class SplitPoint:
    """A candidate split location in a multi-section protocol."""

    line_number: int  # 1-indexed
    heading: str  # the H2/H3 text at the split point
    char_offset: int  # absolute character offset in the file
    segment_chars_before: int  # char count of content up to this point


@dataclass
class RetrievalReport:
    """Whether a target protocol surfaces in the top_k for each probe query."""

    query: str
    top_k: int
    expected_title_fragment: str
    found_rank: int | None  # None if not in top_k
    top_titles: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.found_rank is not None


# --------------------------------------------------------------------------- #
# File-level validation                                                        #
# --------------------------------------------------------------------------- #


def validate_file(path: str | Path) -> list[ProtocolIssue]:
    """Validate a protocol file against the authoring rules.

    Does NOT touch vstash — pure text analysis. Use `ingest_and_verify`
    to check the file also produces exactly one chunk in the KB.
    """
    p = Path(path)
    issues: list[ProtocolIssue] = []

    if not p.exists():
        issues.append(ProtocolIssue(
            path=str(p), severity="error", rule="missing_file",
            message="File does not exist",
        ))
        return issues

    text = p.read_text(encoding="utf-8")

    # H2 header count — the PRIMARY predictor of multi-chunking because
    # vstash splits at every markdown header before looking at size. One
    # H2 per file is the safe ceiling; prefer bold labels for sub-sections.
    h2_matches = list(_H2_RE.finditer(text))
    h3_matches = list(_H3_RE.finditer(text))
    if len(h2_matches) > MAX_H2_SECTIONS:
        headings = [m.group(1).strip() for m in h2_matches]
        issues.append(ProtocolIssue(
            path=str(p), severity="warn", rule="h2_sections",
            message=(
                f"{len(h2_matches)} H2 sections — vstash will likely produce "
                f"{len(h2_matches)} chunks unless small sections merge (<80 tokens)"
            ),
            fix_hint=(
                "Flatten H2 sub-sections to **bold labels** so the file stays as "
                "one vstash chunk. Example: replace `## Treatment` with a paragraph "
                "that starts `**Treatment.**`. Run `medlocal protocol validate` to "
                "confirm the fix. Current H2 headings:\n     - "
                + "\n     - ".join(headings)
            ),
        ))

    # H3 headers also cause splits, though less aggressively since sub-sections
    # tend to be short and merge via the 80-token rule.
    if len(h3_matches) >= 3:
        issues.append(ProtocolIssue(
            path=str(p), severity="info", rule="h3_sections",
            message=f"{len(h3_matches)} H3 sub-sections — check chunk count carefully",
            fix_hint="H3 headers also split chunks before merge. Prefer bold labels.",
        ))

    # Char counts are a soft signal — they predict the amount of content,
    # which predicts chunk pressure when combined with header count.
    n_chars = len(text)
    if n_chars > WARN_CHARS:
        issues.append(ProtocolIssue(
            path=str(p), severity="warn", rule="char_count",
            message=f"{n_chars} chars — file is large; verify chunk count with vstash",
            fix_hint=(
                "Large flat files can still be one chunk, but paragraph-level "
                "splitting may kick in. Run `medlocal protocol validate` to confirm."
            ),
        ))
    elif n_chars > SOFT_TARGET_CHARS:
        issues.append(ProtocolIssue(
            path=str(p), severity="info", rule="char_count",
            message=f"{n_chars} chars — over the soft target of {SOFT_TARGET_CHARS}",
            fix_hint="Still fine if the file is flat (single H2 or none).",
        ))

    # Title (H1)
    first_nonempty = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not _H1_RE.match(first_nonempty):
        issues.append(ProtocolIssue(
            path=str(p), severity="error", rule="missing_h1",
            message="File must start with an H1 title (`# WHO: ...`)",
            fix_hint="Add a `# <title>` line as the first non-blank line.",
        ))

    # Source attribution
    if not _SOURCE_RE.search(text):
        issues.append(ProtocolIssue(
            path=str(p), severity="warn", rule="missing_source",
            message="No Source attribution to WHO / MSF / Hesperian / IMCI found",
            fix_hint="Add a `Source: WHO ...` line citing the authoritative document and year.",
        ))

    # YAML frontmatter breaks vstash chunking in subtle ways
    if _YAML_FRONTMATTER_RE.match(text):
        issues.append(ProtocolIssue(
            path=str(p), severity="warn", rule="yaml_frontmatter",
            message="YAML frontmatter detected — vstash treats it as body text",
            fix_hint="Move metadata into a plain paragraph below the H1 title.",
        ))

    return issues


# --------------------------------------------------------------------------- #
# Split-point suggestions                                                      #
# --------------------------------------------------------------------------- #


def suggest_split_points(path: str | Path) -> list[SplitPoint]:
    """Return candidate split points for a file that is too large.

    Walks the H2 headings in order; each one is a potential split
    boundary. For small files (≤TARGET_CHARS) returns an empty list.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if len(text) <= SOFT_TARGET_CHARS:
        return []

    points: list[SplitPoint] = []
    lines = text.splitlines(keepends=True)
    cum_chars = 0
    for i, line in enumerate(lines):
        m = _H2_RE.match(line.rstrip("\n"))
        if m and i > 0:  # skip the very first heading — nothing before it
            points.append(SplitPoint(
                line_number=i + 1,
                heading=m.group(1).strip(),
                char_offset=cum_chars,
                segment_chars_before=cum_chars,
            ))
        cum_chars += len(line)

    return points


# --------------------------------------------------------------------------- #
# vstash-level validation                                                      #
# --------------------------------------------------------------------------- #


def get_chunk_count(kb: KnowledgeBase, path: str | Path, profile: str = "core") -> int | None:
    """Return the number of chunks a file has in vstash, or None if absent."""
    abs_path = str(Path(path).resolve())
    mem = kb._core if profile == "core" else kb._local
    for d in mem.list():
        if str(Path(d.path).resolve()) == abs_path:
            return d.chunk_count
    return None


def ingest_and_verify(
    kb: KnowledgeBase,
    path: str | Path,
    profile: str = "core",
) -> list[ProtocolIssue]:
    """Ingest a file into the target profile and verify it produces 1 chunk.

    If the file already exists in the KB with a different chunk count,
    this will re-ingest with force=True and re-check. Returns an empty
    list on success, or a list of issues if the file produces >1 chunk.
    """
    issues: list[ProtocolIssue] = []
    abs_path = str(Path(path).resolve())

    # Remove any stale entry first so the chunk count is fresh.
    mem = kb._core if profile == "core" else kb._local
    try:
        mem.remove(abs_path)
    except Exception:
        pass  # first ingest, nothing to remove

    if profile == "core":
        n = kb.ingest_core(abs_path, force=True)
    else:
        n = kb.ingest_local(abs_path, force=True)

    if n == 0:
        issues.append(ProtocolIssue(
            path=abs_path, severity="error", rule="ingest_failed",
            message="vstash ingest produced 0 chunks",
            fix_hint="Check the file has content and a valid markdown body.",
        ))
        return issues

    count = get_chunk_count(kb, abs_path, profile=profile)
    if count is None:
        issues.append(ProtocolIssue(
            path=abs_path, severity="error", rule="ingest_missing",
            message="File ingested but did not appear in KB listing",
        ))
    elif count > 1:
        splits = suggest_split_points(abs_path)
        hint = (
            f"vstash produced {count} chunks because the file has multiple "
            f"markdown headers. Two ways to fix:\n"
            f"     (A) PREFERRED — flatten H2/H3 sub-sections to **bold labels** "
            f"so the file stays as one chunk. Example: replace `## Treatment` "
            f"with a paragraph starting `**Treatment.**`.\n"
            f"     (B) If the content is genuinely too large for one flat file, "
            f"split it into focused sibling files (e.g. "
            f"`foo-diagnosis-who.md` + `foo-treatment-who.md`) at the H2 "
            f"boundaries below:"
        )
        if splits:
            hint += "\n     " + "\n     ".join(
                f"line {s.line_number:3d}  (offset {s.char_offset:4d})  ## {s.heading}"
                for s in splits
            )
        issues.append(ProtocolIssue(
            path=abs_path, severity="error", rule="chunk_count",
            message=f"Produced {count} chunks — should be 1",
            fix_hint=hint,
        ))

    return issues


# --------------------------------------------------------------------------- #
# Corpus-level audit                                                           #
# --------------------------------------------------------------------------- #


def audit_corpus(
    kb: KnowledgeBase,
    protocols_dir: str | Path,
    profile: str = "core",
) -> list[ProtocolIssue]:
    """Audit every protocol in the corpus against all rules.

    Runs in order:
      1. File-level text rules (char count, title, source, frontmatter)
      2. KB chunk count (must be 1 per file)
      3. Stale orphans (chunks in the KB whose source file no longer exists)

    Returns a flat list of ProtocolIssue. Empty list = clean corpus.
    """
    issues: list[ProtocolIssue] = []
    protocols_dir = Path(protocols_dir).resolve()

    disk_files = {
        p.resolve() for p in protocols_dir.rglob("*.md") if p.is_file()
    }

    # File-level rules
    for f in sorted(disk_files):
        issues.extend(validate_file(f))

    # KB-level rules
    mem = kb._core if profile == "core" else kb._local
    kb_docs = {Path(d.path).resolve(): d for d in mem.list()}

    # Stale orphans — in KB but not on disk
    for kb_path in kb_docs:
        if kb_path not in disk_files and str(kb_path).endswith(".md"):
            # Only flag entries that look like they belong to this profile tree
            try:
                kb_path.relative_to(protocols_dir)
            except ValueError:
                continue
            issues.append(ProtocolIssue(
                path=str(kb_path), severity="error", rule="stale_orphan",
                message="Chunks exist in vstash but source file is gone",
                fix_hint=(
                    "Call kb._core.remove('<abs_path>') or delete the core.db and re-ingest.\n"
                    "  Stale orphans pollute FTS rankings and can beat real protocols."
                ),
            ))

    # Chunk count per file
    for f in sorted(disk_files):
        count = kb_docs.get(f.resolve())
        if count is None:
            issues.append(ProtocolIssue(
                path=str(f), severity="warn", rule="not_ingested",
                message="File exists on disk but is not in the KB",
                fix_hint="Run `medlocal ingest data/core/protocols --profile core` to add it.",
            ))
            continue
        if count.chunk_count > 1:
            splits = suggest_split_points(f)
            hint = (
                f"vstash produced {count.chunk_count} chunks ({count.char_count} chars). "
                f"Two fixes:\n"
                f"     (A) PREFERRED — flatten H2/H3 sub-sections to **bold labels** "
                f"so the file stays as one chunk.\n"
                f"     (B) If content is too large for one flat file, split at "
                f"the H2 boundaries below into focused sibling files:"
            )
            if splits:
                hint += "\n     " + "\n     ".join(
                    f"line {s.line_number:3d}  (offset {s.char_offset:4d})  ## {s.heading}"
                    for s in splits
                )
            issues.append(ProtocolIssue(
                path=str(f), severity="error", rule="chunk_count",
                message=f"Produced {count.chunk_count} chunks — should be 1",
                fix_hint=hint,
            ))

    return issues


# --------------------------------------------------------------------------- #
# Retrieval dry-run                                                            #
# --------------------------------------------------------------------------- #


def retrieval_dry_run(
    kb: KnowledgeBase,
    target_title_fragment: str,
    queries: list[str],
    top_k: int = 6,
) -> list[RetrievalReport]:
    """Run each probe query and report whether the target protocol surfaces.

    The target is matched by case-insensitive substring match against the
    chunk title (what vstash reports). Use this to verify that a newly
    authored protocol is actually reachable from realistic CHW queries
    BEFORE shipping it — this is the check that would have caught the
    organophosphate embedder failure at authoring time.
    """
    reports: list[RetrievalReport] = []
    frag = target_title_fragment.lower()
    for q in queries:
        hits = kb.search(q, top_k=top_k)
        rank: int | None = None
        titles: list[str] = []
        for i, h in enumerate(hits, start=1):
            titles.append(h.title)
            if rank is None and frag in h.title.lower():
                rank = i
        reports.append(RetrievalReport(
            query=q,
            top_k=top_k,
            expected_title_fragment=target_title_fragment,
            found_rank=rank,
            top_titles=titles,
        ))
    return reports
