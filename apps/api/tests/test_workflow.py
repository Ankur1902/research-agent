import json

from app.agents.workflow import run_research
from app.core.db import Session
from app.evaluation.metrics import evaluate_report
from app.main import app
from app.models.entities import Research
from app.security.auth import hasher
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


class FakeRedis:
    def __init__(self):
        self.counts = {}
        self.jobs = []

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True

    async def enqueue_job(self, *args, **kwargs):
        self.jobs.append((args, kwargs))
        return "test-job"


async def account(client, email):
    result = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Test Analyst",
            "organization": "Test Organization",
            "email": email,
            "password": "long-enough-password",
        },
    )
    assert result.status_code == 201, result.text
    client.headers["x-csrf-token"] = result.json()["csrf"]


async def test_complete_demo_flow_and_tenant_isolation():
    app.state.redis = FakeRedis()
    app.state.dummy_hash = hasher.hash("dummy-password")
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://localhost:3000"}
    ) as client:
        await account(client, "owner@example.com")
        project = await client.post("/api/v1/projects", json={"name": "India EV Market", "description": "Test project"})
        assert project.status_code == 201
        job_response = await client.post(
            "/api/v1/research",
            json={
                "question": "Demonstrate the research approval workflow",
                "mode": "DEMO",
                "project_id": project.json()["id"],
            },
        )
        assert job_response.status_code == 201, job_response.text
        job_id = job_response.json()["id"]
        await run_research({}, job_id)
        job = (await client.get(f"/api/v1/research/{job_id}")).json()
        assert job["status"] == "WAITING_FOR_APPROVAL"
        assert (await client.post(f"/api/v1/research/{job_id}/approve")).status_code == 200
        await run_research({}, job_id, planning=False)
        # A duplicate queue delivery cannot add more sources or execute again.
        await run_research({}, job_id, planning=False)
        job = (await client.get(f"/api/v1/research/{job_id}")).json()
        assert job["status"] == "REVIEW"
        assert job["cost"] == 0
        assert len((await client.get(f"/api/v1/research/{job_id}/sources")).json()) == 1
        assert (await client.post(f"/api/v1/research/{job_id}/approve")).json()["status"] == "COMPLETED"
        assert (await client.post(f"/api/v1/research/{job_id}/approve")).status_code == 409
        pdf = await client.get(f"/api/v1/research/{job_id}/export?format=pdf")
        assert pdf.content.startswith(b"%PDF")
        import io

        from pypdf import PdfReader

        assert "S1" in "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
        exported = await client.get(f"/api/v1/research/{job_id}/export?format=json")
        assert exported.json()["mode"] == "DEMO"
        evaluation = await client.post(
            "/api/v1/evaluations",
            json={"name": "Fixture evaluation", "research_id": job_id, "expected_topics": ["approval"]},
        )
        assert evaluation.status_code == 201
        assert evaluation.json()["results"]["metrics"]["citation_mapping_precision"] == 1
        stream = await client.get(f"/api/v1/research/{job_id}/events")
        assert "source_found" in stream.text and "checkpoint" in stream.text
        dashboard = (await client.get("/api/v1/dashboard")).json()
        assert dashboard["reports"] == 1 and dashboard["projects"] == 1
        # A second organization cannot access any resource or nested route.
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"Origin": "http://localhost:3000"}
        ) as other:
            await account(other, "other@example.com")
            for path in [
                f"/projects/{project.json()['id']}",
                f"/research/{job_id}",
                f"/research/{job_id}/sources",
                f"/research/{job_id}/trace",
                f"/research/{job_id}/execution",
                f"/research/{job_id}/export",
                f"/research/{job_id}/events",
            ]:
                assert (await other.get("/api/v1" + path)).status_code == 404
        assert (await client.post("/api/v1/auth/logout")).status_code == 200
        assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_csrf_upload_cancel_and_missing_configuration():
    app.state.redis = FakeRedis()
    app.state.dummy_hash = hasher.hash("dummy-password")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"Origin": "http://localhost:3000"}
    ) as client:
        await account(client, "upload@example.com")
        token = client.headers.pop("x-csrf-token")
        assert (await client.post("/api/v1/projects", json={"name": "Forbidden"})).status_code == 403
        client.headers["x-csrf-token"] = token
        upload = await client.post(
            "/api/v1/documents", files={"file": ("../safe.txt", b"Evidence is always inspected.", "text/plain")}
        )
        assert upload.status_code == 201, upload.text
        doc = await client.get(f"/api/v1/documents/{upload.json()['id']}")
        assert doc.json()["name"] == "safe.txt" and doc.json()["chunk_count"] == 1
        live = (
            await client.post(
                "/api/v1/research", json={"question": "Research a real market with unavailable credentials"}
            )
        ).json()
        await run_research({}, live["id"])
        failed = (await client.get(f"/api/v1/research/{live['id']}")).json()
        assert failed["status"] == "FAILED" and "API_KEY" in failed["error"]
        job = (
            await client.post(
                "/api/v1/research", json={"question": "Cancel this research before it starts", "mode": "DEMO"}
            )
        ).json()
        assert (await client.post(f"/api/v1/research/{job['id']}/cancel")).json()["status"] == "CANCELLED"
        await run_research({}, job["id"])
        async with Session() as session:
            assert (await session.scalar(select(Research).where(Research.id == job["id"]))).status == "CANCELLED"


def test_metrics_are_derived_and_unmeasured_are_null():
    result = evaluate_report({"findings": [], "sources": []}, [], [])
    assert all(value is None for value in result.values())
    assert json.dumps(result)
