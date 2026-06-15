"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routes import health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise DB on startup; nothing to tear down on shutdown."""
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="SuoraFlow API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — restricted to the configured frontend origin; never wildcard
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)

    return app


app = create_app()
