"""Offline acceptance cases for the reliability and evidence upgrade."""

import asyncio
import time
from datetime import timedelta

import httpx
import pytest
from app.agents.evidence import pack_evidence
from app.agents.workflow import Workflow, run_research
from app.core.config import settings
from app.core.db import Base, Session
from app.core.local_runtime import LocalQueue
from app.evaluation.metrics import evaluate_report
from app.main import app
from app.models.entities import Organization, Research, RunLease, Source, SpendReservation, Usage, now
from app.rag.pipeline import diversify
from app.schemas.contracts import Plan
from app.services.budgets import reserve
from app.services.providers import StructuredResponseError, validated_completion
from app.workers.recovery import recover_research
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def make_job(session, *, status="PLANNING", monthly_budget=1):
    org = Organization(name="Upgrade fixture", preferences={"monthly_budget": monthly_budget})
    session.add(org)
    await session.flush()
    job = Research(organization_id=org.id, question="What is the notice deadline?", budget=1, status=status)
    session.add(job)
    await session.commit()
    return org, job


async def test_rotating_cookie_cannot_reset_client_limit(monkeypatch):
    monkeypatch.setattr(settings(), "max_requests_per_minute", 2)
    app.state.redis = LocalQueue()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        codes = [
            (await client.get("/api/v1/auth/me", headers={"cookie": f"researchos_session=bogus-{i}"})).status_code
            for i in range(3)
        ]
        assert codes == [401, 401, 429]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("192.0.2.2", 12)), base_url="http://test"
    ) as other:
        assert (await other.get("/api/v1/auth/me")).status_code == 401


def test_later_evidence_and_relevant_source_are_selected():
    irrelevant = [Source(citation=f"S{i}", title="Other", evidence="Unrelated background.") for i in range(10)]
    relevant = Source(citation="S11", title="Policy", evidence="background " * 220 + "Notice deadline: 14 days.")
    packed = pack_evidence([*irrelevant, relevant], "What is the notice deadline?")
    assert packed[0]["citation"] == "S11"
    assert "Notice deadline: 14 days." in packed[0]["untrusted_evidence"]
    assert packed[0]["evidence_offset"] > 0
    assert packed[0]["untrusted_evidence"] in relevant.evidence


def test_source_recall_rejects_query_mentions_and_lookalikes():
    report = {
        "findings": [],
        "sources": [{"citation": "S1", "url": "https://other.invalid/?ref=https://target.invalid/report"}],
    }
    assert evaluate_report(report, [], ["https://target.invalid/report"])["expected_source_recall"] == 0
    report["sources"][0]["url"] = "https://TARGET.invalid:443/report#section"
    assert evaluate_report(report, [], ["https://target.invalid/report"])["expected_source_recall"] == 1


async def test_held_reservations_prevent_shared_allowance_reuse():
    async with Session() as session:
        org, job = await make_job(session, monthly_budget=0.01)
        second = Research(organization_id=org.id, question="Second lightweight question", budget=1)
        session.add(second)
        await session.commit()
        await reserve(session, job, 0.006, "model")
        with pytest.raises(ValueError, match="monthly budget"):
            await reserve(session, second, 0.006, "model")


async def test_concurrent_jobs_cannot_reserve_same_allowance(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'concurrent.sqlite').as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            org, job = await make_job(session, monthly_budget=0.01)
            second = Research(organization_id=org.id, question="Concurrent question", budget=1)
            session.add(second)
            await session.commit()
            ids = [job.id, second.id]

        async def attempt(identifier):
            async with sessions() as session:
                job = await session.get(Research, identifier)
                try:
                    await reserve(session, job, 0.006, "model")
                    return "reserved"
                except ValueError:
                    return "rejected"

        assert sorted(await asyncio.gather(*(attempt(identifier) for identifier in ids))) == ["rejected", "reserved"]
    finally:
        await engine.dispose()


async def test_prior_month_usage_does_not_consume_current_month():
    async with Session() as session:
        org, job = await make_job(session, monthly_budget=0.01)
        month = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        session.add(
            Usage(
                organization_id=org.id,
                research_id=job.id,
                provider="fixture",
                model="fixture",
                input_tokens=1,
                output_tokens=1,
                cost=100,
                latency_ms=1,
                created_at=month - timedelta(days=1),
            )
        )
        await session.commit()
        assert (await reserve(session, job, 0.006, "model")).status == "HELD"


async def test_invalid_model_response_still_records_usage(monkeypatch):
    from app.agents import workflow

    class InvalidProvider:
        async def complete(self, system, data, schema):
            return validated_completion(schema, "{}", 100, 20, time.monotonic(), "invalid-fixture", 1)

    monkeypatch.setattr(workflow, "llm", InvalidProvider)
    async with Session() as session:
        _, job = await make_job(session)
        with pytest.raises(StructuredResponseError):
            await Workflow(session, job).generate("planner", {"question": job.question}, Plan)
        rows = list((await session.scalars(select(Usage))).all())
        assert len(rows) == 1 and rows[0].input_tokens == 100 and rows[0].cost > 0
        assert (await session.scalar(select(SpendReservation))).status == "SETTLED"


async def test_explicit_provider_rejection_releases_hold(monkeypatch):
    from app.agents import workflow
    from app.services.providers import RequestRejected

    class RejectedProvider:
        async def complete(self, *args):
            raise RequestRejected("Provider rejected request (403)")

    monkeypatch.setattr(workflow, "llm", RejectedProvider)
    async with Session() as session:
        _, job = await make_job(session)
        with pytest.raises(RequestRejected):
            await Workflow(session, job).generate("planner", {"question": job.question}, Plan)
        receipt = await session.scalar(select(SpendReservation))
        assert receipt.status == "SETTLED" and receipt.actual_cost == 0 and job.cost == 0


async def test_uncertain_provider_outcome_keeps_hold(monkeypatch):
    from app.agents import workflow

    class UncertainProvider:
        async def complete(self, *args):
            raise RuntimeError("Provider outcome uncertain")

    monkeypatch.setattr(workflow, "llm", UncertainProvider)
    async with Session() as session:
        _, job = await make_job(session)
        with pytest.raises(RuntimeError, match="uncertain"):
            await Workflow(session, job).generate("planner", {"question": job.question}, Plan)
        receipt = await session.scalar(select(SpendReservation))
        assert receipt.status == "HELD" and receipt.amount > 0


@pytest.mark.parametrize("status", ["PLANNING", "RUNNING", "VERIFICATION"])
async def test_abandoned_phases_fail_explicitly_without_replay(status):
    queue = LocalQueue()
    async with Session() as session:
        _, job = await make_job(session, status=status)
        session.add(RunLease(research_id=job.id, expires_at=now() - timedelta(seconds=1)))
        await session.commit()
        await recover_research({"redis": queue})
        await session.refresh(job)
        assert job.status == "FAILED" and "not replayed" in job.error
        assert queue.jobs.empty()


async def test_recovery_preserves_live_lease_and_redispatches_queue_intent():
    queue = LocalQueue()
    async with Session() as session:
        org, job = await make_job(session)
        session.add(RunLease(research_id=job.id, expires_at=now() + timedelta(seconds=300)))
        pending = Research(
            organization_id=org.id,
            question="Queued lightweight question",
            status="APPROVED",
            updated_at=now() - timedelta(seconds=40),
        )
        session.add(pending)
        await session.commit()
        await recover_research({"redis": queue})
        await session.refresh(job)
        assert job.status == "PLANNING"
        name, resource_id, kwargs = queue.jobs.get_nowait()
        assert (name, resource_id, kwargs) == ("run_research", pending.id, {"planning": False})


def test_lexical_and_hybrid_share_document_diversity():
    from app.models.entities import Chunk

    chunks = [Chunk(id=str(i), document_id="a", text=f"Unique passage {i}") for i in range(8)]
    chunks.append(Chunk(id="b", document_id="b", text="Other document passage"))
    assert [item.document_id for item in diversify(chunks)] == ["a", "a", "a", "b"]


async def test_queue_outage_preserves_creation_and_approval_intents():
    class OfflineQueue(LocalQueue):
        async def enqueue_job(self, *args, **kwargs):
            raise ConnectionError("Synthetic queue outage")

    app.state.redis = OfflineQueue()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"origin": settings().public_origin}
    ) as client:
        account = await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Fixture",
                "organization": "Fixture",
                "email": "queue@example.com",
                "password": "long-fixture-password",
            },
        )
        client.headers["x-csrf-token"] = account.json()["csrf"]
        created = await client.post(
            "/api/v1/research", json={"question": "Demonstrate durable queue intents", "mode": "DEMO"}
        )
        assert created.status_code == 201 and created.json()["status"] == "QUEUED"
        identifier = created.json()["id"]
        await run_research({}, identifier)
        approved = await client.post(f"/api/v1/research/{identifier}/approve")
        assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
        budget = await client.get(f"/api/v1/research/{identifier}/budget")
        assert budget.status_code == 200 and budget.json()["held_amount"] == 0
        client.cookies.clear()
        assert (await client.get(f"/api/v1/research/{identifier}/budget")).status_code == 401
