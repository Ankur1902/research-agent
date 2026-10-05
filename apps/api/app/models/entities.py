import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.db import Base
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Entity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class Organization(Entity, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(120))
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class User(Entity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))


class Member(Entity, Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("user_id", "organization_id"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="OWNER")


class LoginSession(Entity, Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class TenantEntity(Entity):
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)


class Project(TenantEntity, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")


class Document(TenantEntity, Base):
    __tablename__ = "documents"
    name: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED")
    error: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), default="")


class Chunk(TenantEntity, Base):
    __tablename__ = "document_chunks"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int] = mapped_column(Integer, default=1)
    section: Mapped[str] = mapped_column(String(120), default="")


class Research(TenantEntity, Base):
    __tablename__ = "research_jobs"
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    depth: Mapped[str] = mapped_column(String(20), default="standard")
    mode: Mapped[str] = mapped_column(String(20), default="LIVE")
    source_mode: Mapped[str] = mapped_column(String(20), default="both")
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", index=True)
    budget: Mapped[float] = mapped_column(Float, default=1)
    cost: Mapped[float] = mapped_column(Float, default=0)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Source(TenantEntity, Base):
    __tablename__ = "sources"
    research_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id"), index=True)
    citation: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(255))
    evidence: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Event(TenantEntity, Base):
    __tablename__ = "agent_runs"
    research_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    agent: Mapped[str] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Usage(TenantEntity, Base):
    __tablename__ = "llm_usage"
    research_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    request_id: Mapped[str] = mapped_column(String(200), default="")
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[int] = mapped_column(Integer)


class Evaluation(TenantEntity, Base):
    __tablename__ = "evaluation_runs"
    name: Mapped[str] = mapped_column(String(200))
    results: Mapped[dict[str, Any]] = mapped_column(JSON)


class Audit(TenantEntity, Base):
    __tablename__ = "audit_logs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(36))
