"""FastAPI application entry point — lifespan, router mounting, startup."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from src.config import settings
from src.ingest.router import router as ingest_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown for background workers and connection pools."""
    # TODO: Initialize ContextStore, warm up tree-sitter grammars, start background workers
    yield
    # TODO: Graceful shutdown


app = FastAPI(
    title="DocSync Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(ingest_router, prefix="/api/v1")