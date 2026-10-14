"""Isolated browser-test API. Synthetic queue, SQLite, and no external credentials."""

import asyncio
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
STATE = ROOT / "test-results/e2e-local"
STATE.mkdir(parents=True, exist_ok=True)
os.environ.update(
    {
        "DATABASE_URL": f"sqlite+aiosqlite:///{(STATE / 'browser.sqlite').as_posix()}",
        "ENVIRONMENT": "development",
        "PUBLIC_ORIGIN": "http://localhost:3100",
        "AUTH_SECRET": secrets.token_hex(32),
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "GOOGLE_API_KEY": "",
        "SEARCH_API_KEY": "",
        "MAX_REQUESTS_PER_MINUTE": "10000",
    }
)

import uvicorn  # noqa: E402
from app.agents.workflow import run_research  # noqa: E402
from app.core.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security.auth import hasher  # noqa: E402
from app.workers.worker import ingest_document  # noqa: E402


class TestQueue:
    def __init__(self):
        self.counts = {}
        self.jobs = asyncio.Queue()

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True

    async def enqueue_job(self, name, resource_id, **kwargs):
        if name not in {"run_research", "ingest_document"}:
            raise ValueError("Unsupported test task")
        await self.jobs.put((name, resource_id, {k: v for k, v in kwargs.items() if not k.startswith("_")}))
        return "isolated-test-task"

    async def worker(self):
        functions = {"run_research": run_research, "ingest_document": ingest_document}
        while True:
            name, resource_id, kwargs = await self.jobs.get()
            try:
                await functions[name]({}, resource_id, **kwargs)
            finally:
                self.jobs.task_done()


@asynccontextmanager
async def test_lifespan(application):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    queue = TestQueue()
    application.state.redis = queue
    application.state.dummy_hash = hasher.hash("isolated-test-password")
    worker = asyncio.create_task(queue.worker())
    try:
        yield
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await engine.dispose()


app.router.lifespan_context = test_lifespan

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8100)
