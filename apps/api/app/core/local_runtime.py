"""Development-only local task queue; production still uses Redis/ARQ."""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class LocalQueue:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.expires: dict[str, float] = {}
        self.jobs: asyncio.Queue = asyncio.Queue()

    async def incr(self, key):
        if self.expires.get(key, float("inf")) <= time.monotonic():
            self.counts.pop(key, None)
            self.expires.pop(key, None)
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        self.expires[key] = time.monotonic() + ttl
        return True

    async def enqueue_job(self, name, resource_id, **kwargs):
        if name not in {"run_research", "ingest_document"}:
            raise ValueError("Unsupported local task")
        await self.jobs.put(
            (name, resource_id, {key: value for key, value in kwargs.items() if not key.startswith("_")})
        )
        return "local-task"

    async def worker(self):
        from app.agents.workflow import run_research
        from app.workers.worker import ingest_document

        handlers = {"run_research": run_research, "ingest_document": ingest_document}
        while True:
            name, resource_id, kwargs = await self.jobs.get()
            try:
                await handlers[name]({}, resource_id, **kwargs)
            except Exception:
                logger.error("Local task failed: %s", name)
            finally:
                self.jobs.task_done()
