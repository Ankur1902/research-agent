"""Real agent state/persistence and offline CLI with injected model/retrieval fixtures."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.agents import workflow
from app.core.db import Session
from app.evaluation.trajectory import SavedTrajectory, WorkflowCase, evaluate_trajectory, normalize_events
from app.models.entities import Document, Event, Organization, Research
from app.schemas.contracts import Analysis, Assessment, Plan, Report
from app.services.providers import Completion, LLMProvider
from app.tools import research as research_tools
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "packages/evals/workflow/cases.v1.jsonl"
CASES = [WorkflowCase.model_validate_json(line) for line in DATASET.read_text().splitlines()]
QUOTE = "The fixture requires approval."


class GraphProvider(LLMProvider):
    def __init__(self, case):
        self.case = case

    async def complete(self, system, data, schema):
        if schema is Plan:
            agents = {
                "web": ["web_researcher"],
                "documents": ["knowledge_agent"],
                "both": ["web_researcher", "knowledge_agent"],
            }[self.case.source_mode]
            payload = {
                "objective": "Synthetic policy research",
                "output_sections": ["Findings"],
                "tasks": [
                    {"id": str(index), "agent": agent, "question": "research approval policy"}
                    for index, agent in enumerate(agents)
                ],
            }
        elif schema is Analysis:
            citation = data["evidence"][0]["citation"]
            computations = []
            if "calculator" in self.case.expectations.per_tool:
                computations = [
                    {
                        "operation": "growth_percent",
                        "values": [100, 125],
                        "citation": citation,
                        "quote": "Recorded values: 100 and 125.",
                    }
                ]
            payload = {
                "findings": [
                    {"text": QUOTE, "kind": "FACT", "citations": [citation], "quote": QUOTE, "status": "VERIFIED"}
                ],
                "limitations": ["Injected test evidence only"],
                "computations": computations,
            }
        elif schema is Assessment:
            payload = {
                "statuses": [
                    "VERIFIED" if finding["kind"] == "FACT" else "PARTIALLY_SUPPORTED"
                    for finding in data["findings"]["findings"]
                ]
            }
        else:
            assert schema is Report
            payload = {
                "title": "Synthetic fixture report",
                "summary": "A scoped evaluation fixture.",
                "sections": [{"title": "Findings", "finding_indices": list(range(len(data["analysis"]["findings"])))}],
                "limitations": data["analysis"]["limitations"],
            }
        return Completion(schema.model_validate(payload), 10, 5, 1, "injected-graph-request", http_attempts=1)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
async def test_real_graph_satisfies_saved_trajectory_and_cli(case, monkeypatch):
    monkeypatch.setattr(workflow, "llm", lambda: GraphProvider(case))

    class SearchFixture:
        async def search(self, query):
            return [{"title": "Public fixture", "url": "https://fixture.example/policy"}]

    async def fetch_fixture(url):
        return f"<html><body>Public fixture. {QUOTE} Recorded values: 100 and 125.</body></html>"

    monkeypatch.setattr(research_tools, "search_provider", lambda: SearchFixture())
    monkeypatch.setattr(research_tools, "fetch_public", fetch_fixture)
    async with Session() as session:
        organization = Organization(name="Isolated trace test")
        session.add(organization)
        await session.flush()
        document = Document(
            organization_id=organization.id,
            name="Fixture policy",
            content_hash="trace-fixture",
            text=f"Organization fixture. {QUOTE}",
            status="INDEXED",
        )
        session.add(document)
        await session.flush()
        document_id = document.id
        job = Research(
            organization_id=organization.id,
            question="Synthetic research policy review",
            source_mode=case.source_mode,
            depth=case.depth,
            mode="LIVE",
            budget=1,
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    async def retrieve_fixture(session, organization_id, query):
        return [
            SimpleNamespace(
                document_id=document_id, text=f"Organization fixture. {QUOTE}", page=1, id="injected-document-chunk"
            )
        ]

    monkeypatch.setattr(workflow, "retrieve", retrieve_fixture)
    await workflow.run_research({}, job_id)
    if case.expected_final_status in {"REVIEW", "CANCELLED"}:
        async with Session() as session:
            job = await session.get(Research, job_id)
            assert job.status == "WAITING_FOR_APPROVAL", job.error
            job.status = "CANCELLED" if case.expected_final_status == "CANCELLED" else "APPROVED"
            await session.commit()
        await workflow.run_research({}, job_id, planning=False)

    async with Session() as session:
        job = await session.get(Research, job_id)
        assert job.status == case.expected_final_status, job.error
        events = list(
            (await session.scalars(select(Event).where(Event.research_id == job_id).order_by(Event.sequence))).all()
        )
        normalized = normalize_events(
            [
                {"sequence": event.sequence, "agent": event.agent, "type": event.type, "details": event.details}
                for event in events
            ]
        )
        trace = SavedTrajectory(case_id=case.id, events=normalized, final_status=job.status, report=job.report)
    result = evaluate_trajectory(case, trace)
    assert result["gate_passed"], result
    artifacts = ROOT / "test-results/trajectories"
    artifacts.mkdir(parents=True, exist_ok=True)
    trace_path = artifacts / f"{case.id}.json"
    trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/trajectory_eval.py"), "--trace", str(trace_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert json.loads(completed.stdout)["gate_passed"]
