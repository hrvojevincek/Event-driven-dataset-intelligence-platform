import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from eventforge.core.config import Settings
from eventforge.core.otel import (
    ATTR_CORRELATION_ID,
    ATTR_JOB_ID,
    agent_span,
    set_event_attributes,
    setup_otel,
)


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter


def test_setup_otel_skips_when_disabled() -> None:
    settings = Settings(otel_enabled=False)
    assert setup_otel(settings) is False


def test_agent_span_sets_pipeline_attributes(span_exporter: InMemorySpanExporter) -> None:
    with agent_span(
        "intake",
        "process",
        correlation_id="corr-1",
        job_id="job-1",
        event_id="evt-1",
    ) as span:
        set_event_attributes(span, model="gpt-4o-mini", token_count=128)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "agent.intake.process"
    assert spans[0].attributes[ATTR_CORRELATION_ID] == "corr-1"
    assert spans[0].attributes[ATTR_JOB_ID] == "job-1"
    assert spans[0].attributes["model"] == "gpt-4o-mini"
    assert spans[0].attributes["token_count"] == 128
