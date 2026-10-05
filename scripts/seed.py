"""Seed clearly labeled example projects into an existing organization."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from app.core.db import Session  # noqa: E402
from app.models.entities import Member, Project, User  # noqa: E402
from sqlalchemy import select  # noqa: E402


async def seed():
    email = os.environ.get("SEED_EMAIL")
    if not email:
        raise SystemExit("Set SEED_EMAIL to an existing account; no default password is created")
    async with Session() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if not user:
            raise SystemExit("Register the seed account first")
        member = await session.scalar(select(Member).where(Member.user_id == user.id))
        for name in ["India EV Market", "AI in Healthcare", "Cloud Infrastructure Market"]:
            existing = await session.scalar(
                select(Project).where(
                    Project.organization_id == member.organization_id, Project.name == f"DEMO · {name}"
                )
            )
            if not existing:
                session.add(
                    Project(
                        organization_id=member.organization_id,
                        name=f"DEMO · {name}",
                        description="Seed project only; contains no real-world findings or performance metrics.",
                    )
                )
        await session.commit()


asyncio.run(seed())
