"""Knowledge base — dual-profile vstash (core + local) with federated search."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vstash import Memory

from .config import MedLocalConfig


@dataclass
class SearchResult:
    """Unified search result from either profile."""

    text: str
    title: str
    score: float
    profile: str  # "core" or "local"
    chunk_id: int


class KnowledgeBase:
    """Dual-profile knowledge base: core (read-only) + local (editable)."""

    def __init__(self, cfg: MedLocalConfig) -> None:
        Path(cfg.core_db).parent.mkdir(parents=True, exist_ok=True)
        Path(cfg.local_db).parent.mkdir(parents=True, exist_ok=True)
        self._core = Memory(db=cfg.core_db, profile="medlocal-core")
        self._local = Memory(db=cfg.local_db, profile="medlocal-local")

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Federated search across both profiles, ranked by score."""
        results: list[SearchResult] = []

        for profile_name, mem in [("core", self._core), ("local", self._local)]:
            hits = mem.search(query, top_k=top_k)
            for h in hits:
                results.append(
                    SearchResult(
                        text=h.text,
                        title=h.title,
                        score=h.score,
                        profile=profile_name,
                        chunk_id=h.chunk_id,
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def ingest_core(self, source: str, *, force: bool = False) -> int:
        """Ingest into core knowledge base. Returns chunk count."""
        results = self._core.add(source, force=force)
        if not results or results[0].status == "error":
            return 0
        return results[0].chunks

    def ingest_local(self, source: str, *, force: bool = False) -> int:
        """Ingest into local knowledge base. Returns chunk count."""
        results = self._local.add(source, force=force)
        if not results or results[0].status == "error":
            return 0
        return results[0].chunks

    def get_chunk(self, chunk_id: int, profile: str = "core") -> str | None:
        """Get chunk text by ID from specified profile."""
        mem = self._core if profile == "core" else self._local
        chunk = mem.get_chunk(chunk_id)
        return chunk.text if chunk else None
