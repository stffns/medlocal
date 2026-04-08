"""Knowledge base — dual-profile vstash (core + local) with federated search."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vstash import Memory
from vstash.embed import embed_query

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
        # Larger chunks for medical protocols — keeps title+symptoms+treatment together
        self._core = Memory(db=cfg.core_db, profile="medlocal-core", chunk_size=2048, chunk_overlap=256)
        self._local = Memory(db=cfg.local_db, profile="medlocal-local", chunk_size=2048, chunk_overlap=256)

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        fts_only: bool = False,
    ) -> list[SearchResult]:
        """Federated search across both profiles, ranked by score.

        When ``fts_only=True`` we run a pure BM25/FTS pass (vec_weight=0,
        fts_weight=1). This is a safety net for queries where the multilingual
        embedder puts the correct clinical chunk far from the query in vector
        space (e.g. "fumigando papas" vs "organophosphate poisoning") — FTS
        finds the chunk at rank 1 but the hybrid RRF drags it down to rank ~13.

        TODO(vstash-upstream): this method reaches into ``mem._store.search``
        and manually calls ``embed_query`` because ``Memory.search()`` does
        NOT forward ``vec_weight``/``fts_weight``/``adaptive_rrf``/
        ``mmr_lambda`` as of vstash 2026-04-07. When the following land
        upstream, collapse this back to ``mem.search(query, top_k=top_k,
        vec_weight=..., fts_weight=..., mmr_lambda=1.0)``:

          1. ``Memory.search`` forwards ``vec_weight``, ``fts_weight``,
             ``adaptive_rrf``, ``mmr_lambda`` to ``_store.search``.
          2. A first-class ``fts_only=True`` flag (or dedicated
             ``Memory.fts_search``) so we do not have to set 0.0/1.0 by hand.
          3. MMR dedup fast-path is a true no-op on single-chunk documents
             (today it can still eliminate them, which is why we force
             ``mmr_lambda=1.0``).
          4. Adaptive RRF reacts to vector-search outcome — when the vector
             candidate pool is empty/tiny, weight should shift toward FTS
             automatically instead of compressing FTS-rank-1 chunks to
             ``fts_weight/(60+1)``.

        See ``memory/project_retrieval_insights.md`` (in the agent memory
        for this repo) for the full debug story, miss_analysis traces, and
        the seven concrete vstash improvement proposals that would let us
        delete this workaround.
        """
        results: list[SearchResult] = []

        vec_w, fts_w = (0.0, 1.0) if fts_only else (0.3, 0.7)
        for profile_name, mem in [("core", self._core), ("local", self._local)]:
            # Clinical protocols are small, densely-termed files where
            # BM25/FTS is the stronger signal. We boost FTS (0.7) over
            # vector (0.3) and disable MMR dedup (which was silently
            # eliminating single-chunk protocols at mmr_lambda=0.5).
            q_emb = embed_query(query, mem._cfg.embeddings.model)
            hits = mem._store.search(
                query_embedding=q_emb,
                query_text=query,
                top_k=top_k,
                vec_weight=vec_w,
                fts_weight=fts_w,
                adaptive_rrf=False,
                mmr_lambda=1.0,
            )
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
