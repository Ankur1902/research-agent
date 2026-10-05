import asyncio

from alembic import context
from app.core.config import settings
from app.core.db import Base
from app.models import entities  # noqa: F401
from sqlalchemy.ext.asyncio import create_async_engine


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_async_engine(settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


asyncio.run(online())
