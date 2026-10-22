"""Recover persisted queue intents and stop abandoned execution safely."""

import logging
from datetime import timedelta
from typing import cast

from app.core.db import Session
from app.models.entities import Event, Research, RunLease, now
from sqlalchemy import CursorResult, func, select, update

logger = logging.getLogger(__name__)


async def recover_research(ctx):
    timestamp = now()
    async with Session() as session:
        # Existing queued/approved rows are the durable queue intent: creation
        # and approval commit them before Redis is contacted.
        pending = list(
            (
                await session.scalars(
                    select(Research)
                    .where(
                        Research.status.in_(["QUEUED", "APPROVED"]),
                        Research.updated_at < timestamp - timedelta(seconds=30),
                    )
                    .order_by(Research.created_at)
                    .limit(100)
                )
            ).all()
        )
        for job in pending:
            planning = job.status == "QUEUED"
            try:
                await ctx["redis"].enqueue_job(
                    "run_research",
                    job.id,
                    planning=planning,
                    # A prior failed ARQ result can retain the original ID for
                    # hours. A bounded recovery slot avoids that tombstone;
                    # the database state claim remains the execution gate.
                    _job_id=f"recover:{'plan' if planning else 'execute'}:{job.id}:{timestamp:%Y%m%d%H%M}:{timestamp.second // 30}",
                )
            except Exception:
                logger.warning("Research queue recovery deferred; queue unavailable")
                break
        abandoned = list(
            (
                await session.scalars(
                    select(Research)
                    .outerjoin(RunLease, RunLease.research_id == Research.id)
                    .where(
                        Research.status.in_(["PLANNING", "RUNNING", "VERIFICATION"]),
                        (RunLease.expires_at < timestamp)
                        | (RunLease.research_id.is_(None) & (Research.updated_at < timestamp - timedelta(seconds=720))),
                    )
                )
            ).all()
        )
        for job in abandoned:
            result = await session.execute(
                update(Research)
                .where(Research.id == job.id, Research.status.in_(["PLANNING", "RUNNING", "VERIFICATION"]))
                .values(
                    status="FAILED",
                    finished_at=timestamp,
                    error=(
                        "Worker interrupted or execution deadline exceeded. Review trace and held budget reservations "
                        "before starting a new run; uncertain provider calls were not replayed."
                    ),
                )
            )
            if cast(CursorResult, result).rowcount:
                sequence = (
                    await session.scalar(select(func.max(Event.sequence)).where(Event.research_id == job.id)) or 0
                )
                session.add(
                    Event(
                        organization_id=job.organization_id,
                        research_id=job.id,
                        sequence=sequence + 1,
                        agent="manager",
                        type="research_interrupted",
                        message="Interrupted execution requires review",
                        details={"automatic_replay": False, "held_reservations_preserved": True},
                    )
                )
        await session.commit()
