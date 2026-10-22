import asyncio
import hashlib
import html
import json
import secrets
from typing import Annotated, cast

from app.core.config import settings
from app.core.db import db
from app.evaluation.execution import execution_summary
from app.evaluation.metrics import evaluate_report
from app.models.entities import (
    Audit,
    Chunk,
    Document,
    Evaluation,
    Event,
    Member,
    Organization,
    Project,
    Research,
    Source,
    SpendReservation,
    Usage,
    User,
    now,
)
from app.rag.pipeline import chunk_text, parse_document
from app.repositories.tenant import owned, serialize
from app.schemas.contracts import Credentials, Preferences, ProjectInput, Register, ResearchInput
from app.security.auth import hasher, issue_session, principal, verify_password
from app.security.guards import require_role
from app.services.reports import export_pdf, markdown
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1")
DB = Annotated[AsyncSession, Depends(db)]
Identity = Annotated[dict, Depends(principal)]
WRITERS = {"OWNER", "ADMIN", "RESEARCHER"}


def audit(session, identity, action, resource_id=None):
    session.add(
        Audit(organization_id=identity["org"], user_id=identity["user"].id, action=action, resource_id=resource_id)
    )


async def enqueue(request, name, resource_id, **kwargs):
    try:
        job = await request.app.state.redis.enqueue_job(name, resource_id, **kwargs)
        if job is None:
            raise HTTPException(409, "Job already queued")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Background queue is unavailable") from None


@router.post("/auth/register", status_code=201)
async def register(body: Register, request: Request, response: Response, session: DB):
    if request.headers.get("origin") != settings().public_origin:
        raise HTTPException(403, "Invalid origin")
    organization = Organization(name=body.organization)
    user = User(
        email=body.email.lower(), name=body.name, password_hash=await asyncio.to_thread(hasher.hash, body.password)
    )
    session.add_all([organization, user])
    try:
        await session.flush()
        session.add(Member(user_id=user.id, organization_id=organization.id, role="OWNER"))
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Account already exists") from None
    return await issue_session(session, user, organization.id, response)


@router.post("/auth/login")
async def login(body: Credentials, request: Request, response: Response, session: DB):
    if request.headers.get("origin") != settings().public_origin:
        raise HTTPException(403, "Invalid origin")
    user = await session.scalar(select(User).where(User.email == body.email.lower()))
    # Dummy Argon2 verification prevents a fast absent-user path.
    encoded = user.password_hash if user else request.app.state.dummy_hash
    valid = await asyncio.to_thread(verify_password, encoded, body.password)
    if not user or not valid:
        raise HTTPException(401, "Invalid email or password")
    member = await session.scalar(select(Member).where(Member.user_id == user.id))
    if not member:
        raise HTTPException(403, "No organization membership")
    audit(session, {"org": member.organization_id, "user": user}, "login")
    return await issue_session(session, user, member.organization_id, response)


@router.get("/auth/me")
async def me(identity: Identity):
    user = identity["user"]
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "organization_id": identity["org"],
        "role": identity["role"],
        "csrf": identity["session"].csrf,
    }


@router.post("/auth/logout")
async def logout(response: Response, session: DB, identity: Identity):
    audit(session, identity, "logout")
    await session.delete(identity["session"])
    await session.commit()
    response.delete_cookie("researchos_session", path="/")
    return {"ok": True}


@router.get("/projects")
async def projects(session: DB, identity: Identity, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    rows = await session.scalars(
        select(Project)
        .where(Project.organization_id == identity["org"])
        .order_by(Project.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [serialize(row) for row in rows]


@router.post("/projects", status_code=201)
async def create_project(body: ProjectInput, session: DB, identity: Identity):
    require_role(identity["role"], WRITERS)
    project = Project(organization_id=identity["org"], **body.model_dump())
    session.add(project)
    await session.flush()
    audit(session, identity, "project_created", project.id)
    await session.commit()
    return serialize(project)


@router.get("/projects/{project_id}")
async def project(project_id: str, session: DB, identity: Identity):
    return serialize(await owned(session, Project, project_id, identity["org"]))


@router.get("/research")
async def researches(
    session: DB, identity: Identity, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    rows = await session.scalars(
        select(Research)
        .where(Research.organization_id == identity["org"])
        .order_by(Research.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [serialize(row) for row in rows]


@router.post("/research", status_code=201)
async def create_research(body: ResearchInput, request: Request, session: DB, identity: Identity):
    require_role(identity["role"], WRITERS)
    if body.project_id:
        await owned(session, Project, body.project_id, identity["org"])
    job = Research(organization_id=identity["org"], **body.model_dump())
    session.add(job)
    await session.flush()
    audit(session, identity, "research_started", job.id)
    await session.commit()
    try:
        await enqueue(request, "run_research", job.id, _job_id=f"plan:{job.id}")
    except HTTPException:
        # The committed QUEUED row remains a durable intent for worker recovery.
        pass
    return serialize(job)


@router.get("/research/{research_id}")
async def research(research_id: str, session: DB, identity: Identity):
    return serialize(await owned(session, Research, research_id, identity["org"]))


@router.post("/research/{research_id}/approve")
async def approve(research_id: str, request: Request, session: DB, identity: Identity):
    require_role(identity["role"], WRITERS)
    job = await owned(session, Research, research_id, identity["org"])
    target = {"WAITING_FOR_APPROVAL": "APPROVED", "REVIEW": "COMPLETED"}.get(job.status)
    if not target:
        raise HTTPException(409, "Research is not awaiting approval")
    previous = job.status
    result = await session.execute(
        update(Research)
        .where(Research.id == job.id, Research.status == previous)
        .values(status=target, finished_at=now() if target == "COMPLETED" else None)
    )
    if not cast(CursorResult, result).rowcount:
        raise HTTPException(409, "Research state changed")
    audit(session, identity, "research_approved", job.id)
    await session.commit()
    if target == "APPROVED":
        try:
            await enqueue(request, "run_research", job.id, planning=False, _job_id=f"execute:{job.id}")
        except HTTPException:
            # Preserve approval; recovery dispatches this durable intent later.
            pass
    await session.refresh(job)
    return serialize(job)


@router.post("/research/{research_id}/cancel")
async def cancel(research_id: str, session: DB, identity: Identity):
    require_role(identity["role"], WRITERS)
    job = await owned(session, Research, research_id, identity["org"])
    if job.status in {"COMPLETED", "CANCELLED", "FAILED"}:
        raise HTTPException(409, "Research is already terminal")
    job.status = "CANCELLED"
    audit(session, identity, "research_cancelled", job.id)
    await session.commit()
    return serialize(job)


@router.get("/research/{research_id}/sources")
async def sources(research_id: str, session: DB, identity: Identity):
    await owned(session, Research, research_id, identity["org"])
    return [
        serialize(row)
        for row in await session.scalars(
            select(Source).where(Source.research_id == research_id, Source.organization_id == identity["org"])
        )
    ]


@router.get("/research/{research_id}/trace")
async def trace(research_id: str, session: DB, identity: Identity):
    await owned(session, Research, research_id, identity["org"])
    return [
        serialize(row)
        for row in await session.scalars(
            select(Event)
            .where(Event.research_id == research_id, Event.organization_id == identity["org"])
            .order_by(Event.sequence)
        )
    ]


@router.get("/research/{research_id}/execution")
async def execution_details(research_id: str, session: DB, identity: Identity):
    job = await owned(session, Research, research_id, identity["org"])
    events = list((await session.scalars(select(Event).where(Event.research_id == research_id,
                   Event.organization_id == identity["org"]).order_by(Event.sequence))).all())
    return execution_summary(job, events)


@router.get("/research/{research_id}/usage")
async def usage(research_id: str, session: DB, identity: Identity):
    await owned(session, Research, research_id, identity["org"])
    return [
        serialize(row)
        for row in await session.scalars(
            select(Usage).where(Usage.research_id == research_id, Usage.organization_id == identity["org"])
        )
    ]


@router.get("/research/{research_id}/budget")
async def budget_details(research_id: str, session: DB, identity: Identity):
    job = await owned(session, Research, research_id, identity["org"])
    receipts = list((await session.scalars(select(SpendReservation).where(
        SpendReservation.research_id == research_id, SpendReservation.organization_id == identity["org"]
    ).order_by(SpendReservation.created_at))).all())
    held = sum(row.amount for row in receipts if row.status == "HELD")
    return {"budget": job.budget, "estimated_spend": job.cost, "held_amount": held,
            "available_amount": max(0, job.budget - job.cost - held),
            "requires_reconciliation": bool(held) and job.status in {"FAILED", "CANCELLED"},
            "reservations": [serialize(row) for row in receipts]}


@router.get("/research/{research_id}/events")
async def stream(research_id: str, request: Request, session: DB, identity: Identity, after: int = Query(0, ge=0)):
    await owned(session, Research, research_id, identity["org"])
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        raise HTTPException(400, "Invalid event cursor") from None

    async def events():
        nonlocal cursor
        from app.core.db import Session

        for _ in range(600):
            if await request.is_disconnected():
                return
            async with Session() as stream_session:
                rows = list(
                    (
                        await stream_session.scalars(
                            select(Event)
                            .where(
                                Event.research_id == research_id,
                                Event.organization_id == identity["org"],
                                Event.sequence > cursor,
                            )
                            .order_by(Event.sequence)
                        )
                    ).all()
                )
                for row in rows:
                    cursor = row.sequence
                    yield f"id: {cursor}\ndata: {json.dumps(serialize(row), default=str)}\n\n"
                job = await owned(stream_session, Research, research_id, identity["org"])
                yield f"event: state\ndata: {json.dumps({'status': job.status, 'cost': job.cost})}\n\n"
                if job.status in {"COMPLETED", "FAILED", "CANCELLED", "WAITING_FOR_APPROVAL", "REVIEW"}:
                    yield "event: checkpoint\ndata: {}\n\n"
                    return
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/research/{research_id}/export")
async def export(
    research_id: str,
    session: DB,
    identity: Identity,
    format: str = Query("markdown", pattern="^(markdown|html|pdf|json)$"),
):
    job = await owned(session, Research, research_id, identity["org"])
    if not job.report:
        raise HTTPException(409, "Report is not ready")
    audit(session, identity, "report_exported", job.id)
    await session.commit()
    extensions = {"markdown": "md", "html": "html", "pdf": "pdf", "json": "json"}
    content: bytes | str
    if format == "pdf":
        content, media = await asyncio.to_thread(export_pdf, job.report), "application/pdf"
    elif format == "json":
        content, media = json.dumps(job.report), "application/json"
    elif format == "html":
        content, media = (
            "<!doctype html><meta charset='utf-8'><title>ResearchOS report</title><pre>"
            + html.escape(markdown(job.report))
            + "</pre>",
            "text/html",
        )
    else:
        content, media = markdown(job.report), "text/markdown"
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="research-{job.id}.{extensions[format]}"'},
    )


@router.get("/documents")
async def documents(
    session: DB, identity: Identity, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    rows = await session.scalars(
        select(Document)
        .where(Document.organization_id == identity["org"])
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [{key: value for key, value in serialize(row).items() if key != "text"} for row in rows]


@router.post("/documents", status_code=201)
async def upload(file: UploadFile, request: Request, session: DB, identity: Identity):
    require_role(identity["role"], WRITERS)
    content = await file.read(settings().max_upload_bytes + 1)
    if len(content) > settings().max_upload_bytes:
        raise HTTPException(413, "Document exceeds 10 MB")
    name = (file.filename or "document.txt").replace("\\", "/").split("/")[-1][:255]
    try:
        pages = await asyncio.to_thread(parse_document, name, content)
    except Exception as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else "Document could not be parsed") from None
    document = Document(
        organization_id=identity["org"],
        name=name,
        content_hash=hashlib.sha256(content).hexdigest(),
        text="\n".join(text for _, text in pages),
    )
    session.add(document)
    await session.flush()
    for page, text in pages:
        for part in chunk_text(text):
            session.add(Chunk(organization_id=identity["org"], document_id=document.id, text=part, page=page))
    audit(session, identity, "document_uploaded", document.id)
    await session.commit()
    try:
        await enqueue(request, "ingest_document", document.id, _job_id=f"ingest:{document.id}")
    except HTTPException:
        document.status = "FAILED"
        document.error = "Background queue unavailable"
        await session.commit()
        raise
    return {key: value for key, value in serialize(document).items() if key != "text"}


@router.get("/documents/{document_id}")
async def document(document_id: str, session: DB, identity: Identity):
    doc = await owned(session, Document, document_id, identity["org"])
    return {
        **serialize(doc),
        "chunk_count": await session.scalar(select(func.count(Chunk.id)).where(Chunk.document_id == doc.id)),
    }


@router.post("/documents/{document_id}/retry")
async def retry_document(document_id: str, request: Request, session: DB, identity: Identity):
    require_role(identity["role"], WRITERS)
    document = await owned(session, Document, document_id, identity["org"])
    if document.status != "FAILED":
        raise HTTPException(409, "Only failed documents can be retried")
    await enqueue(request, "ingest_document", document.id, _job_id=f"ingest:{document.id}:{secrets.token_hex(4)}")
    return {"ok": True}


@router.get("/dashboard")
async def dashboard(session: DB, identity: Identity):
    jobs = list((await session.scalars(select(Research).where(Research.organization_id == identity["org"]))).all())
    counts: dict[str, int] = {}
    for job in jobs:
        day = job.created_at.date().isoformat()
        counts[day] = counts.get(day, 0) + 1
    completed = [job for job in jobs if job.status == "COMPLETED"]
    durations = [(job.finished_at - job.created_at).total_seconds() for job in completed if job.finished_at]
    return {
        "projects": await session.scalar(
            select(func.count(Project.id)).where(Project.organization_id == identity["org"])
        ),
        "documents": await session.scalar(
            select(func.count(Document.id)).where(
                Document.organization_id == identity["org"], Document.status == "INDEXED"
            )
        ),
        "active": sum(job.status in {"QUEUED", "PLANNING", "APPROVED", "RUNNING", "VERIFICATION"} for job in jobs),
        "reports": len(completed),
        "cost": sum(job.cost for job in jobs),
        "average_duration": sum(durations) / len(durations) if durations else None,
        "volume": counts,
        "recent": [serialize(job) for job in sorted(jobs, key=lambda job: job.created_at, reverse=True)[:6]],
    }


class EvalInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    research_id: str
    expected_topics: list[str] = Field(default_factory=list, max_length=100)
    expected_sources: list[str] = Field(default_factory=list, max_length=100)


@router.get("/evaluations")
async def evaluations(session: DB, identity: Identity):
    return [
        serialize(row)
        for row in await session.scalars(
            select(Evaluation)
            .where(Evaluation.organization_id == identity["org"])
            .order_by(Evaluation.created_at.desc())
            .limit(100)
        )
    ]


@router.get("/evaluations/{evaluation_id}")
async def evaluation(evaluation_id: str, session: DB, identity: Identity):
    return serialize(await owned(session, Evaluation, evaluation_id, identity["org"]))


@router.post("/evaluations", status_code=201)
async def evaluate(body: EvalInput, session: DB, identity: Identity):
    require_role(identity["role"], WRITERS)
    job = await owned(session, Research, body.research_id, identity["org"])
    if not job.report:
        raise HTTPException(409, "Select a research job with a report")
    metrics = evaluate_report(job.report, body.expected_topics, body.expected_sources)
    run = Evaluation(
        organization_id=identity["org"],
        name=body.name,
        results={
            "metrics": metrics,
            "research_id": job.id,
            "mode": job.mode,
            "cost": job.cost,
            "method": "deterministic provenance and topic matching; support statuses are model assessments",
            "expected_topics": body.expected_topics,
            "expected_sources": body.expected_sources,
        },
    )
    session.add(run)
    await session.commit()
    return serialize(run)


@router.get("/settings")
async def get_settings(session: DB, identity: Identity):
    organization = await session.get(Organization, identity["org"])
    if organization is None:
        raise HTTPException(404, "Organization not found")
    config = settings()
    return {
        "organization": organization.name,
        "preferences": organization.preferences,
        "role": identity["role"],
        "provider": config.llm_provider,
        "model": config.llm_model,
        "search_provider": config.search_provider,
        "generation_configured": bool(
            {
                "openai": config.openai_api_key,
                "anthropic": config.anthropic_api_key,
                "gemini": config.google_api_key,
            }.get(config.llm_provider)
        ),
        "search_configured": bool(config.search_api_key),
        "embedding_configured": bool(config.openai_api_key),
    }


@router.patch("/settings")
async def save_settings(body: Preferences, session: DB, identity: Identity):
    require_role(identity["role"], {"OWNER", "ADMIN"})
    organization = await session.get(Organization, identity["org"])
    if organization is None:
        raise HTTPException(404, "Organization not found")
    organization.preferences = body.model_dump()
    audit(session, identity, "settings_changed", organization.id)
    await session.commit()
    return organization.preferences
