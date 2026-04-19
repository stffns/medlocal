"""Lightweight search API for the Android app.

Exposes MedLocal's full retrieval pipeline (hybrid vec+FTS, 4-pass
_multi_query_search) as an HTTP endpoint that the Android app can
call over local network. The LLM inference stays on-device (Gemma 4);
only the retrieval is delegated to the laptop where vstash runs natively.

Usage:
    python -m medlocal.search_api [--port 8766]

The Android app calls:
    POST /search {"query": "aspirin child fever", "top_k": 6}
    → [{"chunk_id": 963, "title": "Infant Safety", "text": "...", "score": 0.0156}]
"""

from __future__ import annotations

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

from .config import load_config
from .knowledge import KnowledgeBase

logger = logging.getLogger(__name__)

_kb: KnowledgeBase | None = None


def _get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        cfg = load_config()
        _kb = KnowledgeBase(cfg)
        logger.info("KnowledgeBase initialized")
    return _kb


class SearchHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        if self.path == "/search":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            query = body.get("query", "")
            top_k = body.get("top_k", 6)
            fts_only = body.get("fts_only", False)

            kb = _get_kb()
            results = kb.search(query, top_k=top_k, fts_only=fts_only)

            data = [
                {
                    "chunk_id": r.chunk_id,
                    "title": r.title,
                    "text": r.text,
                    "score": r.score,
                    "profile": r.profile,
                }
                for r in results
            ]
            self._json(200, data)

        elif self.path == "/multi_search":
            # Full _multi_query_search with preflight — same as consult pipeline
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            query = body.get("query", "")
            top_k = body.get("top_k", 6)
            preflight_terms = body.get("preflight_terms", "")

            from .consult import _multi_query_search
            from .preflight import preflight as run_preflight
            from .config import load_config
            cfg = load_config()
            kb = _get_kb()

            # Run preflight if terms not provided
            if not preflight_terms:
                try:
                    pf = run_preflight(query, cfg.llm)
                    preflight_terms = " ".join(pf.get("clinical_terms", []))
                except Exception:
                    pass

            all_results, keywords = _multi_query_search(kb, query, cfg.llm, preflight_terms=preflight_terms)
            results = all_results[:top_k]
            logger.info("multi_search: %d results, keywords=%s, preflight=%s", len(results), keywords[:60], preflight_terms[:60])

            data = [
                {
                    "chunk_id": r.chunk_id,
                    "title": r.title,
                    "text": r.text,
                    "score": r.score,
                    "profile": r.profile,
                }
                for r in results
            ]

            self._json(200, data)
        else:
            self._json(404, {"error": "not found"})

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok", "protocols": 75})
        else:
            self._json(404, {"error": "not found"})

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    _get_kb()  # pre-load
    server = HTTPServer(("0.0.0.0", args.port), SearchHandler)
    print(f"MedLocal search API on http://0.0.0.0:{args.port}")
    print(f"Android: POST http://<laptop-ip>:{args.port}/search")
    server.serve_forever()


if __name__ == "__main__":
    main()
