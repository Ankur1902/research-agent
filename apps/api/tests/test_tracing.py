"""Tracing contract: coherent traces, event linkage, no tenant content in telemetry, resilient export."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from app.agents import workflow
from app.agents.workflow import run_research
from app.core import telemetry
from app.core.config import settings
from app.core.db import Session
from app.models.entities import Event, Organization, Research
from app.schemas.contracts import Plan
from app.services.providers import FailoverProvider, ProviderUnavailable
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from sqlalchemy import select
from test_failover import Scripted, chain  # noqa: F401,F811
from test_live_graph import FixtureProvider

QUESTION_MARKER = "ZEBRA-QUESTION-93"
EVIDENCE_MARKER = "OKAPI-EVIDENCE-77"


@pytest.fixture
def spans():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry.use_provider(provider)
    yield exporter
    telemetry.use_provider(None)


def dump(finished) -> str:
    """Everything a telemetry backend would receive, as one string."""
    parts = []
    for item in finished:
        parts += [item.name, json.dumps(dict(item.attributes or {}), default=str), item.status.description or ""]
        for entry in item.events:
            parts += [entry.name, json.dumps(dict(entry.attributes or {}), default=str)]
    return "\n".join(parts)


def test_everything_is_a_noop_without_a_provider():
    telemetry.use_provider(None)
    with telemetry.span("anything", {"a": 1}):
        telemetry.annotate({"b": 2})
        telemetry.event("e")
        assert telemetry.current_trace_id() is None
        assert telemetry.trace_ref() == {}


def test_failed_span_records_only_the_error_type(spans):
    with pytest.raises(ValueError):
        with telemetry.span("work", {"keep": "me", "dropped": None}):
            raise ValueError("tenant-secret-in-message")
    (finished,) = spans.get_finished_spans()
    assert finished.attributes["error.type"] == "ValueError" and finished.attributes["keep"] == "me"
    assert "dropped" not in finished.attributes
    assert finished.status.status_code.name == "ERROR" and finished.status.description == "ValueError"
    assert finished.events == ()  # no exception event, which would carry the message
    assert "tenant-secret-in-message" not in dump([finished])


def test_unsampled_traces_do_not_advertise_a_trace_id():
    telemetry.use_provider(TracerProvider(sampler=ParentBased(TraceIdRatioBased(0))))
    try:
        with telemetry.span("dropped"):
            assert telemetry.trace_ref() == {}
    finally:
        telemetry.use_provider(None)


async def run_pipeline(monkeypatch, provider, question):
    from app.tools import research as tools

    class FixtureSearch:
        async def search(self, query):
            return [{"title": "Fixture evidence", "url": "https://fixture.example/report"}]

    async def fixture_fetch(url):
        return f"<html><body>The fixture reports 25 percent growth. Recorded values: 100 and 125. {EVIDENCE_MARKER}</body></html>"

    monkeypatch.setattr(workflow, "llm", lambda: provider)
    monkeypatch.setattr(tools, "search_provider", lambda: FixtureSearch())
    monkeypatch.setattr(tools, "fetch_public", fixture_fetch)
    monkeypatch.setattr(settings(), "organization_budget", 50)
    async with Session() as session:
        org = Organization(name="Tracing test")
        session.add(org)
        await session.flush()
        job = Research(organization_id=org.id, question=question, source_mode="web", mode="LIVE", budget=1)
        session.add(job)
        await session.commit()
        job_id = job.id
    await run_research({}, job_id)
    async with Session() as session:
        job = await session.get(Research, job_id)
        job.status = "APPROVED"
        await session.commit()
    await run_research({}, job_id, planning=False)
    return job_id


async def test_pipeline_emits_one_coherent_trace_per_phase(monkeypatch, spans):
    job_id = await run_pipeline(
        monkeypatch, FixtureProvider(), f"Investigate {QUESTION_MARKER} growth in fixture markets"
    )
    finished = spans.get_finished_spans()
    names = [item.name for item in finished]
    for expected in (
        "research.run",
        "agent.planner",
        "agent.analyst",
        "agent.verifier",
        "agent.writer",
        "research.collect_web",
        "tool.web_search",
        "tool.fetch_webpage",
        "tool.calculator",
    ):
        assert expected in names, expected

    runs = {item.attributes["researchos.phase"]: item for item in finished if item.name == "research.run"}
    assert set(runs) == {"planning", "execution"}
    assert runs["planning"].context.trace_id != runs["execution"].context.trace_id
    assert all(item.attributes["researchos.research_id"] == job_id for item in runs.values())

    by_id = {item.context.span_id: item for item in finished}

    def root_of(item):
        while item.parent is not None:
            item = by_id[item.parent.span_id]
        return item

    # Every span hangs off the research.run of its own phase, and phases never share a trace.
    for item in finished:
        assert root_of(item).name == "research.run"
    assert root_of(next(i for i in finished if i.name == "agent.planner")) is runs["planning"]
    assert root_of(next(i for i in finished if i.name == "agent.analyst")) is runs["execution"]
    assert next(i for i in finished if i.name == "tool.fetch_webpage").parent.span_id in {
        i.context.span_id for i in finished if i.name == "research.collect_web"
    }

    analyst = next(item for item in finished if item.name == "agent.analyst")
    assert analyst.attributes["gen_ai.operation.name"] == "chat"
    assert analyst.attributes["gen_ai.usage.input_tokens"] == 100
    assert analyst.attributes["gen_ai.usage.output_tokens"] == 50
    assert analyst.attributes["gen_ai.response.id"] == "fixture-request"
    assert analyst.attributes["researchos.cost.estimated_usd"] > 0
    assert len(analyst.attributes["researchos.prompt_sha256"]) == 64

    # Persisted events carry the trace id, so the in-app trace view can link to the backend.
    async with Session() as session:
        events = {
            event.type: event
            for event in await session.scalars(select(Event).where(Event.research_id == job_id))
            if event.type in {"planning_started", "execution_authorized"}
        }
    assert events["planning_started"].details["trace_id"] == format(runs["planning"].context.trace_id, "032x")
    assert events["execution_authorized"].details["trace_id"] == format(runs["execution"].context.trace_id, "032x")


async def test_tenant_content_never_reaches_telemetry(monkeypatch, spans):
    await run_pipeline(monkeypatch, FixtureProvider(), f"Investigate {QUESTION_MARKER} growth in fixture markets")
    exported = dump(spans.get_finished_spans())
    assert exported  # the dump is non-empty, so the absence checks below mean something
    for private in (QUESTION_MARKER, EVIDENCE_MARKER, "Fixture report", "fixture.example", "A fabricated claim"):
        assert private not in exported, private


class Exploding:
    async def complete(self, system, data, schema):
        raise ValueError("leaky-provider-message")


async def test_failed_run_flags_the_span_without_leaking_the_message(monkeypatch, spans):
    job_id = await run_pipeline(monkeypatch, Exploding(), f"Investigate {QUESTION_MARKER} please now")
    finished = spans.get_finished_spans()
    run = next(item for item in finished if item.name == "research.run")
    assert run.attributes["researchos.outcome"] == "failed" and run.attributes["error.type"] == "ValueError"
    assert run.status.status_code.name == "ERROR"
    assert "leaky-provider-message" not in dump(finished)
    async with Session() as session:
        assert (await session.get(Research, job_id)).status == "FAILED"


async def test_failover_skips_are_visible_on_the_active_span(chain, spans):  # noqa: F811
    Scripted.script = {"openai:p": [ProviderUnavailable("down")], "anthropic:s": [None]}
    assert isinstance(chain, FailoverProvider)
    with telemetry.span("agent.test"):
        await chain.complete("sys", {}, Plan)
    (finished,) = spans.get_finished_spans()
    (skip,) = finished.events
    assert skip.name == "failover.skip"
    assert dict(skip.attributes) == {"target": "openai:p", "reason": "unavailable", "breaker_state": "closed"}


def test_a_broken_exporter_never_raises(monkeypatch):
    telemetry.use_provider(None)
    monkeypatch.setattr(settings(), "otel_traces_exporter", "console")

    def boom(*args, **kwargs):
        raise RuntimeError("exporter exploded")

    monkeypatch.setattr(telemetry, "TracerProvider", boom)
    assert telemetry.setup_tracing() is None
    with telemetry.span("still works"):
        pass


def test_spans_reach_an_otlp_collector_over_http(monkeypatch):
    received = []

    class Collector(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path, self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        telemetry.use_provider(None)
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setattr(settings(), "otel_traces_exporter", "otlp")
        provider = telemetry.setup_tracing("wire-test")
        assert provider is not None
        with telemetry.span("wire.span", {"researchos.research_id": "r-1"}):
            pass
        assert provider.force_flush()
    finally:
        telemetry.shutdown_tracing()
        telemetry.use_provider(None)
        server.shutdown()
    ((path, body),) = received
    assert path == "/v1/traces"
    request = ExportTraceServiceRequest.FromString(body)
    resource = request.resource_spans[0]
    assert {a.key: a.value.string_value for a in resource.resource.attributes}["service.name"] == "wire-test"
    exported = resource.scope_spans[0].spans[0]
    assert exported.name == "wire.span"
    assert {a.key: a.value.string_value for a in exported.attributes} == {"researchos.research_id": "r-1"}
