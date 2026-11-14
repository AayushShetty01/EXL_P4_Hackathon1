"""Entry point of factory_core: creates the API, allows the dashboard origin and registers the routes.

Run from the factory_core folder: uvicorn app.main:app --port 8000
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine
from sqlmodel import Session, select
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import audit_api, files_api, models_api, results_api, runs_api
from app.api.api_errors import http_error_handler, unexpected_error_handler, validation_error_handler
from app.api_schemas import HealthStatus
from app.config import SERVICE_NAME, SERVICE_VERSION, Settings, load_settings
from app.database import ModelRow, create_database_engine
from app.estate_scanner import EstateScanError, register_estate
from app.llm_client import Provider
from app.pipeline_context import PipelineContext
from app.pipeline_runner import PipelineRunner
from app.sample_model import register_sample_model

logger = logging.getLogger("factory_core")


def register_on_startup(engine: Engine, settings: Settings) -> None:
    """Scan the estate at every start; if that fails and nothing is registered, fall back to the sample."""
    with Session(engine) as session:
        try:
            found = register_estate(session, settings)
            logger.info("Estate scan registered %d models", len(found))
        except EstateScanError as error:
            logger.error("Estate scan failed at startup: %s", error.message)
            if session.exec(select(ModelRow)).first() is None:
                register_sample_model(session, settings)


def create_app(
    settings: Settings | None = None,
    *,
    llm_provider: Provider | None = None,
    service_transport: httpx.BaseTransport | None = None,
    background: bool = True,
    recover_runs: bool = True,
) -> FastAPI:
    """Build the FastAPI application; tests pass their own settings, LLM provider and service transport.

    recover_runs=False opens the app read only for exports, without resuming any run.
    """
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Open the database, register models and start the pipeline runner before the first request."""
        engine = create_database_engine(settings.database_path)
        app.state.engine = engine
        register_on_startup(engine, settings)
        context = PipelineContext(settings, engine, llm_provider=llm_provider, service_transport=service_transport)
        app.state.runner = PipelineRunner(context, background=background)
        if recover_runs:
            app.state.runner.recover_interrupted_runs()
        yield
        app.state.runner.close()
        engine.dispose()

    app = FastAPI(
        title="factory_core",
        version=SERVICE_VERSION,
        description="ModelPassport orchestrator: inventory, agents, human gates, audit trail.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)

    @app.get("/health", response_model=HealthStatus, tags=["health"])
    def health() -> HealthStatus:
        """Service health in the shared contract shape."""
        return HealthStatus(status="ok", service=SERVICE_NAME, version=SERVICE_VERSION)

    for module in (models_api, runs_api, results_api, audit_api, files_api):
        app.include_router(module.router)
    return app


app = create_app()
