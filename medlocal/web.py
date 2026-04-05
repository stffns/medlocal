"""MedLocal Web UI — serves the React frontend build."""

from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import app

_STATIC_DIR = Path(__file__).parent / "static"

# Serve static assets (JS, CSS, images)
app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")


@app.get("/favicon.svg")
def favicon():
    return FileResponse(_STATIC_DIR / "favicon.svg")


@app.get("/icons.svg")
def icons():
    return FileResponse(_STATIC_DIR / "icons.svg")


@app.get("/")
def serve_ui():
    """Serve the React frontend."""
    return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")
