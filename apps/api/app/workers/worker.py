from app.agents.workflow import run_research
from app.core.config import settings
from app.core.db import Session
from app.models.entities import Document
from app.rag.pipeline import index_document
from arq.connections import RedisSettings


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


class WorkerSettings:
    functions = [run_research, ingest_document]
    redis_settings = RedisSettings.from_dsn(settings().redis_url)
    max_jobs = 4
    job_timeout = 660
    max_tries = 2
