"""
Minimal FastAPI server for the local viewer.

Serves GET /api/runs, GET /api/runs/{run_id}, GET /api/runs/{run_id}/events,
and GET / with static index.html. No CORS by default.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

import agentdbg.storage as storage
from agentdbg.config import load_config

SPEC_VERSION = "0.1"
UI_STATIC_DIR = Path(__file__).resolve().parent / "ui_static"
UI_INDEX_PATH = UI_STATIC_DIR / "index.html"
UI_STYLES_PATH = UI_STATIC_DIR / "styles.css"
UI_APP_JS_PATH = UI_STATIC_DIR / "app.js"
FAVICON_PATH = UI_STATIC_DIR / "favicon.svg"


def create_app() -> FastAPI:
    """Create and return the FastAPI application for the local viewer."""
    app = FastAPI(title="AgentDbg Viewer")

    @app.get("/api/runs")
    def get_runs() -> dict:
        """List recent runs. Response: { spec_version, runs }."""
        config = load_config()
        runs = storage.list_runs(limit=50, config=config)
        return {"spec_version": SPEC_VERSION, "runs": runs}

    @app.get("/api/runs/{run_id}")
    def get_run_meta(run_id: str) -> dict:
        """Return run.json metadata for the given run_id."""
        config = load_config()
        try:
            return storage.load_run_meta(run_id, config)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid run_id")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="run not found")

    @app.get("/api/runs/{run_id}/events")
    def get_run_events(run_id: str) -> dict:
        """Return events array for the run. 404 if run not found."""
        config = load_config()
        try:
            storage.load_run_meta(run_id, config)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid run_id")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="run not found")
        try:
            events = storage.load_events(run_id, config)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid run_id")
        return {
            "spec_version": SPEC_VERSION,
            "run_id": run_id,
            "events": events,
        }

    @app.get("/favicon.svg")
    def serve_favicon() -> FileResponse:
        """Serve favicon to avoid 404 and improve polish."""
        if not FAVICON_PATH.is_file():
            raise HTTPException(status_code=404, detail="favicon not found")
        return FileResponse(FAVICON_PATH, media_type="image/svg+xml")

    @app.get("/styles.css")
    def serve_styles() -> FileResponse:
        """Serve UI stylesheet."""
        if not UI_STYLES_PATH.is_file():
            raise HTTPException(status_code=404, detail="styles not found")
        return FileResponse(UI_STYLES_PATH, media_type="text/css")

    @app.get("/app.js")
    def serve_app_js() -> FileResponse:
        """Serve UI application script."""
        if not UI_APP_JS_PATH.is_file():
            raise HTTPException(status_code=404, detail="app.js not found")
        return FileResponse(UI_APP_JS_PATH, media_type="application/javascript")

    @app.get("/")
    def serve_ui() -> FileResponse:
        """Serve the static HTML UI with content-type text/html."""
        if not UI_INDEX_PATH.is_file():
            raise HTTPException(
                status_code=404,
                detail="UI not found: agentdbg/ui_static/index.html is missing",
            )
        return FileResponse(
            UI_INDEX_PATH,
            media_type="text/html",
        )

    return app
