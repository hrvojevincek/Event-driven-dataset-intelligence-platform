"""OpenTelemetry setup and span helpers for EventForge."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from eventforge.core.config import Settings

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

_initialized = False

ATTR_CORRELATION_ID = "correlation_id"
ATTR_JOB_ID = "job_id"
ATTR_EVENT_ID = "event_id"
ATTR_AGENT_NAME = "agent_name"
ATTR_MODEL = "model"
ATTR_TOKEN_COUNT = "token_count"


def setup_otel(settings: Settings, *, service_name: str | None = None) -> bool:
    """Configure OTLP trace export. Returns False when OTEL is disabled."""
    global _initialized
    if _initialized:
        return settings.otel_enabled

    if not settings.otel_enabled or not settings.otel_exporter_otlp_endpoint.strip():
        logger.info("OpenTelemetry disabled")
        return False

    name = service_name or settings.otel_service_name
    resource = Resource.create(
        {
            "service.name": name,
            "deployment.environment": settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _initialized = True
    logger.info(
        "OpenTelemetry configured (service=%s endpoint=%s)",
        name,
        settings.otel_exporter_otlp_endpoint,
    )
    return True


def instrument_fastapi(app: Any) -> None:
    """Auto-instrument FastAPI when OTEL is active."""
    if not _initialized:
        return
    FastAPIInstrumentor.instrument_app(app)


def get_tracer(name: str = "eventforge") -> trace.Tracer:
    """Return a tracer for manual spans."""
    return trace.get_tracer(name)


def set_event_attributes(
    span: trace.Span,
    *,
    correlation_id: str | None = None,
    job_id: str | None = None,
    event_id: str | None = None,
    agent_name: str | None = None,
    model: str | None = None,
    token_count: int | None = None,
) -> None:
    """Attach standard EventForge attributes to a span."""
    if correlation_id:
        span.set_attribute(ATTR_CORRELATION_ID, correlation_id)
    if job_id:
        span.set_attribute(ATTR_JOB_ID, job_id)
    if event_id:
        span.set_attribute(ATTR_EVENT_ID, event_id)
    if agent_name:
        span.set_attribute(ATTR_AGENT_NAME, agent_name)
    if model:
        span.set_attribute(ATTR_MODEL, model)
    if token_count is not None:
        span.set_attribute(ATTR_TOKEN_COUNT, token_count)


@contextmanager
def agent_span(
    agent_name: str,
    action: str,
    *,
    correlation_id: str | None = None,
    job_id: str | None = None,
    event_id: str | None = None,
) -> Iterator[trace.Span]:
    """Create a span named agent.{name}.{action} with pipeline attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(f"agent.{agent_name}.{action}") as span:
        set_event_attributes(
            span,
            correlation_id=correlation_id,
            job_id=job_id,
            event_id=event_id,
            agent_name=agent_name,
        )
        yield span


def traced_stage(stage_name: str, action: str = "process") -> Callable[[
    Callable[P, R]],
        Callable[P, R]]:
    """Decorator for async stage handlers that receive an event as the third argument."""

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            event = kwargs.get("event")
            if event is None and len(args) >= 3:
                event = args[2]

            correlation_id = getattr(event, "correlation_id", None)
            job_id = str(getattr(event, "job_id", "")
                         ) if event is not None else None
            event_id = str(getattr(event, "event_id", "")
                           ) if event is not None else None

            with agent_span(
                stage_name,
                action,
                correlation_id=correlation_id,
                job_id=job_id,
                event_id=event_id,
            ):
                return await fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


# Backward-compatible alias — prefer traced_stage in new code.
traced_agent = traced_stage
