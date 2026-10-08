import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.health import router as health_router
from app.core.config import Settings
from app.core.database import create_client, ping
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)
    client = create_client(settings.mongo_uri)
    app.state.mongo_client = client
    db_status = "ok" if await ping(client) else "error"
    logger.info("server.started", extra={"details": {"version": __version__, "db": db_status}})
    try:
        yield
    finally:
        await client.close()
        logger.info("server.stopped", extra={"details": {"version": __version__}})


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Jogo da Velha Multiplayer", version=__version__, lifespan=lifespan)
    app.state.settings = settings or Settings()
    app.include_router(health_router)
    return app
