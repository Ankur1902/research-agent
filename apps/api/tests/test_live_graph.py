"""Live graph regression with explicitly injected provider and network fixtures."""

from app.agents.workflow import run_research
from app.core.db import Session
from app.models.entities import Organization, Research, Source, Usage
from app.schemas.contracts import Analysis, Assessment, Plan
from app.services.providers import Completion
from sqlalchemy import func, select


class FixtureProvider:
    async def complete(self, system, data, schema):
        if schema is Plan:
            value = {
                "objective": "Fixture research",
                "tasks": [{"id": "one", "question": "fixture evidence", "agent": "web_researcher"}],
                "output_sections": ["Findings"],
            }
        elif schema is Analysis:
            value = {
                "findings": [
                    {
                        "text": "The fixture describes a 25 percent growth rate.",
                        "kind": "FACT",
                        "citations": ["S1"],
                        "quote": "The fixture reports 25 percent growth.",
                        "status": "VERIFIED",
                    },
                    {
                        "text": "A fabricated claim must be downgraded.",
                        "kind": "FACT",
                        "citations": ["S999"],
                        "quote": "An invented quote.",
                        "status": "VERIFIED",
                    },
                ],
                "limitations": ["Test fixture only"],
                "computations": [
                    {
                        "operation": "growth_percent",
                        "values": [100, 125],
                        "citation": "S1",
                        "quote": "Recorded values: 100 and 125.",
                    },
                    {"operation": "sum", "values": [999], "citation": "S1", "quote": "Recorded values: 100 and 125."},
                ],
            }
        elif schema is Assessment:
            value = {"statuses": ["VERIFIED"] * len(data["findings"]["findings"])}
        else:
            value = {
                "title": "Fixture report",
                "summary": "A test of provenance constraints.",
                "sections": [{"title": "Findings", "finding_indices": [0, 1, 2]}],
                "limitations": ["Injected provider fixtures"],
            }
        return Completion(schema.model_validate(value), 100, 50, 12, "fixture-request")


async def test_live_graph_with_injected_provider_and_real_persistence(monkeypatch):
    from app.agents import workflow
    from app.core.config import settings
    from app.tools import research as tools

    monkeypatch.setattr(workflow, "llm", lambda: FixtureProvider())

    class FixtureSearch:
        async def search(self, query):
            return [{"title": "Fixture evidence", "url": "https://fixture.example/report"}]

    monkeypatch.setattr(tools, "search_provider", lambda: FixtureSearch())

    async def fixture_fetch(url):
        return "<html><body>The fixture reports 25 percent growth. Recorded values: 100 and 125.</body></html>"

    monkeypatch.setattr(tools, "fetch_public", fixture_fetch)
    config = settings()
    monkeypatch.setattr(config, "organization_budget", 50)
    async with Session() as session:
        org = Organization(name="Live graph test")
        session.add(org)
        await session.flush()
        job = Research(
            organization_id=org.id,
            question="Test graph verification against fixture evidence",
            source_mode="web",
            mode="LIVE",
            budget=1,
        )
        session.add(job)
        await session.commit()
        job_id = job.id
    await run_research({}, job_id)
    async with Session() as session:
        job = await session.get(Research, job_id)
        assert job.status == "WAITING_FOR_APPROVAL"
        job.status = "APPROVED"
        await session.commit()
    await run_research({}, job_id, planning=False)
    async with Session() as session:
        job = await session.get(Research, job_id)
        assert job.status == "REVIEW", job.error
        assert job.report["findings"][0]["status"] == "VERIFIED"
        assert job.report["findings"][1]["status"] == "UNSUPPORTED"
        assert job.report["findings"][1]["citations"] == []
        assert "growth_percent" in job.report["findings"][2]["text"]
        assert ": 25." in job.report["findings"][2]["text"]
        assert len(job.report["findings"]) == 3
        assert await session.scalar(select(func.count(Source.id))) == 1
        assert await session.scalar(select(func.count(Usage.id))) == 4
        assert job.cost > 0
