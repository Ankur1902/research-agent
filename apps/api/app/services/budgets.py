"""Database-serialized admission and durable estimated-spend receipts."""

from typing import cast

from app.core.config import settings
from app.models.entities import Organization, Research, SpendReservation, Usage, now
from sqlalchemy import CursorResult, func, select, update


async def reserve(session, job, amount: float, kind: str) -> SpendReservation:
    if amount < 0:
        raise ValueError("Reservation amount cannot be negative")
    # End any earlier read snapshot before taking the organization write lock.
    # This matters with MySQL's default REPEATABLE READ isolation.
    await session.commit()
    # A write lock serializes admission per organization on MySQL and SQLite.
    # Do not hold it while waiting on a provider.
    await session.execute(
        update(Organization).where(Organization.id == job.organization_id).values(name=Organization.name)
    )
    organization = await session.get(Organization, job.organization_id, populate_existing=True)
    if organization is None:
        raise ValueError("Organization no longer exists")
    month = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    held = (
        select(SpendReservation)
        .where(SpendReservation.organization_id == job.organization_id, SpendReservation.status == "HELD")
        .subquery()
    )
    organization_held = await session.scalar(select(func.coalesce(func.sum(held.c.amount), 0)))
    job_held = await session.scalar(
        select(func.coalesce(func.sum(held.c.amount), 0)).where(held.c.research_id == job.id)
    )
    usage = await session.scalar(
        select(func.coalesce(func.sum(Usage.cost), 0)).where(
            Usage.organization_id == job.organization_id, Usage.created_at >= month
        )
    )
    searches = await session.scalar(
        select(func.coalesce(func.sum(SpendReservation.actual_cost), 0)).where(
            SpendReservation.organization_id == job.organization_id,
            SpendReservation.kind == "search",
            SpendReservation.status == "SETTLED",
            SpendReservation.created_at >= month,
        )
    )
    current_cost = await session.scalar(select(Research.cost).where(Research.id == job.id))
    if float(current_cost or 0) + float(job_held or 0) + amount > job.budget:
        await session.rollback()
        raise ValueError("Insufficient research budget for next call")
    ceiling = organization.preferences.get("monthly_budget", settings().organization_budget)
    if float(usage or 0) + float(searches or 0) + float(organization_held or 0) + amount > ceiling:
        await session.rollback()
        raise ValueError("Organization monthly budget exhausted")
    receipt = SpendReservation(organization_id=job.organization_id, research_id=job.id, kind=kind, amount=amount)
    session.add(receipt)
    await session.commit()
    return receipt


async def settle(session, job, receipt: SpendReservation, cost: float):
    result = await session.execute(
        update(SpendReservation)
        .where(SpendReservation.id == receipt.id, SpendReservation.status == "HELD")
        .values(status="SETTLED", actual_cost=cost)
    )
    if not cast(CursorResult, result).rowcount:
        await session.rollback()
        raise RuntimeError("Spend reservation already settled")
    await session.execute(update(Research).where(Research.id == job.id).values(cost=Research.cost + cost))
    await session.commit()
    await session.refresh(job)
