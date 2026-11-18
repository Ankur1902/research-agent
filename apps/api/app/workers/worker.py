from app.agents.workflow import run_research
from app.core.config import settings
from app.core.db import Session
from app.core.telemetry import setup_tracing, shutdown_tracing
from app.models.entities import Document, LoginSession, now
from app.rag.pipeline import index_document
from app.workers.recovery import recover_research
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import delete


async def ingest_document(ctx, document_id):
    async with Session() as session:
        document = await session.get(Document, document_id)
        if not document or document.status == "INDEXED":
            return
        try:
            document.status = "PROCESSING"
            await session.commit()
            await index_document(session, document)
        except Exception as exc:
            await session.rollback()
            await session.refresh(document)
            document.status = "FAILED"
            document.error = str(exc)[:300] if isinstance(exc, ValueError) else f"Indexing failed: {type(exc).__name__}"
            await session.commit()


async def purge_expired_sessions(ctx):
    """Expired sessions already fail authentication; this keeps the table from growing forever."""
    async with Session() as session:
        await session.execute(delete(LoginSession).where(LoginSession.expires_at < now()))
        await session.commit()


async def startup(ctx):
    setup_tracing()
    await recover_research(ctx)


async def shutdown(ctx):
    shutdown_tracing()  # flush queued spans before the process exits


class WorkerSettings:
    functions = [run_research, ingest_document]
    redis_settings = RedisSettings.from_dsn(settings().redis_url)
    max_jobs = 4
    job_timeout = 660
    max_tries = 2
    on_startup = startup
    on_shutdown = shutdown
    cron_jobs = [
        cron(recover_research, second={0, 30}, unique=True),
        cron(purge_expired_sessions, minute={17}, second={0}, unique=True),
    ]
