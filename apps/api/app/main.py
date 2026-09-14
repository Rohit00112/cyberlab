"""FastAPI application entrypoint for IIC CyberLab."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.badges import router as badges_router
from app.api.challenges import router as challenges_router
from app.api.competitions import router as competitions_router
from app.api.health import router as health_router
from app.api.hints import router as hints_router
from app.api.labs import router as labs_router
from app.api.leaderboard import router as leaderboard_router
from app.api.metrics import metrics_router
from app.api.middleware import RequestContextMiddleware
from app.api.paths import router as paths_router
from app.api.recommendations import router as recommendations_router
from app.api.research import router as research_router
from app.api.skills import router as skills_router
from app.api.submissions import router as submissions_router
from app.api.users import router as users_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from app.services.maintenance import lab_maintenance_loop

    stop_event = asyncio.Event()
    task = asyncio.create_task(lab_maintenance_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        await task


def create_app() -> FastAPI:
    show_docs = not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if show_docs else None,
        openapi_url="/openapi.json" if show_docs else None,
        redoc_url="/redoc" if show_docs else None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(metrics_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(badges_router, prefix="/api/v1")
    app.include_router(challenges_router, prefix="/api/v1")
    app.include_router(competitions_router, prefix="/api/v1")
    app.include_router(submissions_router, prefix="/api/v1")
    app.include_router(hints_router, prefix="/api/v1")
    app.include_router(labs_router, prefix="/api/v1")
    app.include_router(leaderboard_router, prefix="/api/v1")
    app.include_router(skills_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(paths_router, prefix="/api/v1")
    app.include_router(recommendations_router, prefix="/api/v1")
    app.include_router(research_router, prefix="/api/v1")
    return app


app = create_app()