import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

import pytest_asyncio  # noqa: E402
from app.core.db import Base, engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def database():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
