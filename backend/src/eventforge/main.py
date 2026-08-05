import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from eventforge import __version__
from eventforge.api.handlers import register_exception_handlers
from eventforge.api.routes import health, v1
from eventforge.core.config import get_settings
from eventforge.core.logging import setup_logging
from eventforge.core.otel import instrument_fastapi, setup_otel

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging(settings)
    setup_otel(settings)
    logger.info("EventForge API starting (environment=%s)", settings.environment)
    yield


app = FastAPI(
    title="EventForge API",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(v1.router, prefix="/api/v1", tags=["api"])

instrument_fastapi(app)
