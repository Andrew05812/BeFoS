from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.observability import RequestContextMiddleware
from app.websocket.chat_ws import router as ws_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    os.makedirs(settings.upload_dir, exist_ok=True)
    logger.info("BeFoS backend starting (env=%s)", settings.environment)
    yield
    logger.info("BeFoS backend shutting down")


def create_app() -> FastAPI:
    # The OpenAPI document lists every route that takes an object identifier, with the parameter
    # names, and `/docs` is a form that lets anyone send a request from the browser. In
    # development and on the stand that is the fastest way to read the contract; in production it
    # is a map handed to whoever asks for it, so all three are switched off together.
    expose_api_docs = not settings.is_production
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="1.0.0",
        description="BeFoS — compatibility-first dating backend.",
        lifespan=lifespan,
        docs_url="/docs" if expose_api_docs else None,
        redoc_url="/redoc" if expose_api_docs else None,
        openapi_url="/openapi.json" if expose_api_docs else None,
    )

    origins = settings.cors_origin_list or ["*"]
    # Wildcard origin must never be paired with credentials (cookies/auth headers);
    # browsers reject it and it signals a misconfiguration.
    allow_credentials = "*" not in origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )
    # Added last so it sits outermost: every response, including one CORS rejected it,
    # carries the id a caller can quote when reporting a problem.
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.include_router(ws_router)

    os.makedirs(settings.upload_dir, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

    @app.get("/", tags=["root"])
    async def root() -> dict:
        body = {"app": settings.app_name, "status": "ok"}
        # Pointing at /docs in production would advertise a route this file switched off.
        if expose_api_docs:
            body["docs"] = "/docs"
        return body

    return app


app = create_app()
