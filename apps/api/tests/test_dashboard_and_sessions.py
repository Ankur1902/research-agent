from datetime import datetime, timedelta

from app.core.db import Session
from app.main import app
from app.models.entities import LoginSession, Organization, Research, User, now
from app.security.auth import hasher
from app.workers.worker import purge_expired_sessions
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from test_workflow import FakeRedis, account

DAY = datetime(2026, 11, 2, 9, 0)
SEED = [
    # (status, day offset, cost, minutes to finish or None)
    ("COMPLETED", 0, 0.25, 30),
    ("COMPLETED", 0, 0.10, 90),
    ("COMPLETED", 1, 0.05, None),  # completed without finished_at: counted, excluded from duration
    ("RUNNING", 1, 0.02, None),
    ("QUEUED", 2, 0.0, None),
    ("WAITING_FOR_APPROVAL", 2, 0.0, None),
    ("FAILED", 3, 0.40, None),
    ("CANCELLED", 3, 0.0, None),
    ("APPROVED", 4, 0.0, None),
]


def reference(jobs):
    """The previous in-memory algorithm, kept as the oracle for the SQL version."""
    counts = {}
    for job in jobs:
        counts[job.created_at.date().isoformat()] = counts.get(job.created_at.date().isoformat(), 0) + 1
    completed = [job for job in jobs if job.status == "COMPLETED"]
    durations = [(job.finished_at - job.created_at).total_seconds() for job in completed if job.finished_at]
    return {
        "active": sum(job.status in {"QUEUED", "PLANNING", "APPROVED", "RUNNING", "VERIFICATION"} for job in jobs),
        "reports": len(completed),
        "cost": sum(job.cost for job in jobs),
        "average_duration": sum(durations) / len(durations) if durations else None,
        "volume": counts,
        "recent": [job.id for job in sorted(jobs, key=lambda job: job.created_at, reverse=True)[:6]],
    }


async def test_sql_dashboard_matches_the_previous_algorithm_and_stays_tenant_scoped():
    app.state.redis = FakeRedis()
    app.state.dummy_hash = hasher.hash("dummy-password")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"Origin": "http://localhost:3000"}
    ) as client:
        await account(client, "owner@example.com")
        org_id = (await client.get("/api/v1/auth/me")).json()["organization_id"]
        async with Session() as session:
            jobs = []
            for i, (status, offset, cost, minutes) in enumerate(SEED):
                created = DAY + timedelta(days=offset, minutes=i)
                jobs.append(
                    Research(
                        organization_id=org_id,
                        question=f"Seeded question {i}",
                        status=status,
                        cost=cost,
                        created_at=created,
                        finished_at=created + timedelta(minutes=minutes) if minutes else None,
                    )
                )
            other = Organization(name="Other tenant")
            session.add(other)
            await session.flush()
            session.add_all(jobs)
            session.add(
                Research(
                    organization_id=other.id,
                    question="Other tenant run",
                    status="COMPLETED",
                    cost=9.0,
                    created_at=DAY,
                    finished_at=DAY + timedelta(hours=5),
                )
            )
            await session.commit()
            expected = reference(jobs)
        result = (await client.get("/api/v1/dashboard")).json()
    assert result["active"] == expected["active"] == 3
    assert result["reports"] == expected["reports"] == 3
    assert abs(result["cost"] - expected["cost"]) < 1e-9 and abs(result["cost"] - 0.82) < 1e-9
    assert result["average_duration"] == expected["average_duration"] == 3600.0
    assert result["volume"] == expected["volume"]
    assert sorted(result["volume"]) == ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
    assert [row["id"] for row in result["recent"]] == expected["recent"]


async def test_dashboard_with_no_research_is_empty_not_an_error():
    app.state.redis = FakeRedis()
    app.state.dummy_hash = hasher.hash("dummy-password")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"Origin": "http://localhost:3000"}
    ) as client:
        await account(client, "empty@example.com")
        result = (await client.get("/api/v1/dashboard")).json()
    assert result["active"] == result["reports"] == 0
    assert result["cost"] == 0 and result["average_duration"] is None
    assert result["volume"] == {} and result["recent"] == []


async def test_purge_removes_only_expired_sessions():
    async with Session() as session:
        org = Organization(name="Session org")
        user = User(email="s@example.com", name="S", password_hash="x")
        session.add_all([org, user])
        await session.flush()
        for name, delta in (("expired", -timedelta(minutes=1)), ("live", timedelta(days=1))):
            session.add(
                LoginSession(
                    token_hash=name.ljust(64, "0"),
                    user_id=user.id,
                    organization_id=org.id,
                    csrf="c",
                    expires_at=now() + delta,
                )
            )
        await session.commit()
    await purge_expired_sessions({})
    async with Session() as session:
        remaining = [row.token_hash[:7] for row in await session.scalars(select(LoginSession))]
    assert remaining == ["live000"]
