"""Opt-in OpenTelemetry tracing.

Spans carry identifiers, hashes, counts, token usage, cost and error *types* only. Questions, prompts,
evidence, tool arguments and exception messages are never recorded, so enabling tracing does not copy
tenant content into a telemetry backend. When no exporter is configured every call here is a no-op.
"""

import logging
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any

from app.core.config import settings
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger("researchos.telemetry")

# A private provider (not the process-global one) keeps this module self-contained and testable.
_provider: TracerProvider | None = None


def setup_tracing(service_name: str | None = None) -> TracerProvider | None:
    """Configure tracing once. Never raises: a broken exporter must not stop research."""
    global _provider
    config = settings()
    if _provider is not None or config.otel_traces_exporter == "none":
        return _provider
    try:
        if config.otel_traces_exporter == "console":
            exporter: Any = ConsoleSpanExporter()
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter()
        provider = TracerProvider(
            resource=Resource.create({"service.name": service_name or config.otel_service_name}),
            sampler=ParentBased(TraceIdRatioBased(config.otel_sample_ratio)),
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
    except Exception:
        logger.warning("Tracing disabled: exporter could not be configured", exc_info=False)
        return None
    _provider = provider
    return provider


def use_provider(provider: TracerProvider | None) -> None:
    """Install a provider directly (tests)."""
    global _provider
    _provider = provider


def shutdown_tracing() -> None:
    """Flush queued spans; called when a worker stops."""
    if _provider is not None:
        try:
            _provider.shutdown()
        except Exception:
            logger.warning("Tracing shutdown failed", exc_info=False)


def tracer() -> trace.Tracer:
    return _provider.get_tracer("researchos") if _provider else trace.NoOpTracer()


def set_attributes(target: trace.Span, attributes: Mapping[str, Any] | None) -> None:
    for key, value in (attributes or {}).items():
        if value is not None:
            target.set_attribute(key, value)


def annotate(attributes: Mapping[str, Any]) -> None:
    """Add attributes to the active span."""
    set_attributes(trace.get_current_span(), attributes)


def event(name: str, attributes: Mapping[str, Any] | None = None) -> None:
    trace.get_current_span().add_event(name, {k: v for k, v in (attributes or {}).items() if v is not None})


@contextmanager
def span(name: str, attributes: Mapping[str, Any] | None = None):
    # Exception *messages* can quote user content, so only the type is recorded.
    with tracer().start_as_current_span(name, record_exception=False, set_status_on_exception=False) as current:
        set_attributes(current, attributes)
        try:
            yield current
        except BaseException as exc:
            current.set_attribute("error.type", type(exc).__name__)
            current.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise


def mark_failed(exc: BaseException) -> None:
    """Flag the active span as failed without recording the exception message."""
    current = trace.get_current_span()
    current.set_attribute("error.type", type(exc).__name__)
    current.set_status(Status(StatusCode.ERROR, type(exc).__name__))


def current_trace_id() -> str | None:
    """Hex trace id of the active sampled span, so persisted events can link to the backend."""
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid and context.trace_flags.sampled else None


def trace_ref() -> dict[str, str]:
    trace_id = current_trace_id()
    return {"trace_id": trace_id} if trace_id else {}
