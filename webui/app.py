import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from webui.api import create_router
from webui.jobs import JobRunner
from webui.storage import Database


def create_app(database=None, runner=None):
    db = database or Database(
        os.environ.get("WEBUI_DATA_DIR", ""), os.environ.get("WEBUI_KEY_FILE", "")
    )
    jobs = runner or JobRunner(db)

    @asynccontextmanager
    async def lifespan(_app):
        db.initialize()
        jobs.start()
        try:
            yield
        finally:
            jobs.stop()

    app = FastAPI(
        title="AutoDeployKit", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.database = db
    app.state.runner = jobs
    app.include_router(create_router(db, jobs))
    static = Path(__file__).parent / "static"
    app.mount("/assets", StaticFiles(directory=static), name="assets")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid_input(_request: Request, _exc: ValueError):
        return JSONResponse({"detail": "请求参数无效"}, status_code=400)

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    return app
