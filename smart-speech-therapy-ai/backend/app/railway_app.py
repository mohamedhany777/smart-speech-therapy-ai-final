from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.main import app

STATIC_DIR = (Path(__file__).resolve().parent.parent / "static").resolve()
INDEX_FILE = STATIC_DIR / "index.html"

if INDEX_FILE.is_file():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path in {"api", "health", "ready"}:
            raise HTTPException(status_code=404, detail="Not found")
        if full_path:
            candidate = (STATIC_DIR / full_path).resolve()
            if candidate.is_file() and STATIC_DIR in candidate.parents:
                return FileResponse(candidate)
        return FileResponse(INDEX_FILE, headers={"Cache-Control": "no-cache"})