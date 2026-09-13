"""FastAPI application entrypoint for IIC CyberLab."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.challenges import router as challenges_router
from app.api.health import router as health_router
from app.api.hints import router as hints_router
from app.api.leaderboard import router as leaderboard_router
from app.api.submissions import router as submissions_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(challenges_router, prefix="/api/v1")
    app.include_router(submissions_router, prefix="/api/v1")
    app.include_router(hints_router, prefix="/api/v1")
    app.include_router(leaderboard_router, prefix="/api/v1")
    return app


app = create_app()