"""Docker-free development API with real configured LLM calls and lexical retrieval."""

import asyncio
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "apps/api"))
STATE = ROOT / "test-results/e2e-local"
STATE.mkdir(parents=True, exist_ok=True)
os.environ.update(
    {
        "DATABASE_URL": f"sqlite+aiosqlite:///{(STATE / 'browser.sqlite').as_posix()}",
        "ENVIRONMENT": "development",
        "PUBLIC_ORIGIN": "http://localhost:3100",
        "AUTH_SECRET": secrets.token_hex(32),
        "RETRIEVAL_BACKEND": "lexical",
    }
)

import uvicorn  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import Base, engine  # noqa: E402
from app.core.local_runtime import LocalQueue  # noqa: E402
from app.main import app  # noqa: E402
from app.security.auth import hasher  # noqa: E402


@asynccontextmanager
async def local_lifespan(application):
    if settings().environment != "development":
        raise RuntimeError("Local queue is for development only")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    queue = LocalQueue()
    application.state.redis = queue
    application.state.dummy_hash = hasher.hash("local-dummy-password")
    worker = asyncio.create_task(queue.worker())
    try:
        yield
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await engine.dispose()


app.router.lifespan_context = local_lifespan

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8100)
