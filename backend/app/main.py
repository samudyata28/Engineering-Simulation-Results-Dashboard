from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import Settings, get_settings
from .db import init_db, make_engine, make_session_factory
from .services import demands, importer

log = logging.getLogger("dashboard")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.sync_on_startup:
            with session_factory() as db:
                rep = importer.sync(db, settings, trigger="startup")
                log.warning("startup import: %s", rep)
        yield

    app = FastAPI(title="Simulation Results Dashboard API", version="1.0", lifespan=lifespan)
    app.state.settings, app.state.session_factory = settings, session_factory
    app.include_router(router)

    dist = settings.frontend_dist
    if (dist / "index.html").is_file():  # single-process deployment: serve the built SPA
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = (dist / path).resolve()
            if path and dist.resolve() in f.parents and f.is_file():
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    return app


