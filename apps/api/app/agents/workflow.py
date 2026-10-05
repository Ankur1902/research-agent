import asyncio
import json
import re
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

from app.core.config import settings
from app.core.db import Session
from app.models.entities import Document, Event, Organization, Research, Source, Usage, now
from app.rag.pipeline import retrieve
from app.schemas.contracts import Analysis, Assessment, Finding, Plan, Report
from app.security.guards import detect_injection, digest
from app.services.providers import llm
from app.tools.registry import registry
from app.tools.research import research_tools
from bs4 import BeautifulSoup
from sqlalchemy import CursorResult, func, select, update

PROMPTS = Path(__file__).resolve().parents[4] / "packages" / "prompts"


class Stopped(Exception):
    pass


class Workflow:
    def __init__(self, session, job):
        self.session, self.job = session, job
        self.steps = 0
        self.tools = research_tools(lambda query: retrieve(self.session, self.job.organization_id, query))

    async def checkpoint(self):
        await self.session.refresh(self.job)
        if self.job.status == "CANCELLED":
            raise Stopped()
        if self.job.cost >= self.job.budget:
            raise ValueError("Research budget exhausted")
        organization = await self.session.get(Organization, self.job.organization_id)
        used = (
            await self.session.scalar(
                select(func.sum(Research.cost)).where(Research.organization_id == self.job.organization_id)
            )
            or 0
        )
        if used >= organization.preferences.get("monthly_budget", settings().organization_budget):
            raise ValueError("Organization budget exhausted")

    async def transition(self, expected: str, target: str):
        # Compare-and-swap prevents an in-flight worker from undoing cancellation.
        await self.session.flush()
        result = await self.session.execute(
            update(Research).where(Research.id == self.job.id, Research.status == expected).values(status=target)
        )
        if not cast(CursorResult, result).rowcount:
            await self.session.rollback()
            await self.session.refresh(self.job)
            raise Stopped()
        await self.session.commit()
        await self.session.refresh(self.job)

    async def event(self, agent, kind, message, details=None):
        sequence = await self.session.scalar(select(func.count(Event.id)).where(Event.research_id == self.job.id)) or 0
        self.session.add(
            Event(
                organization_id=self.job.organization_id,
                research_id=self.job.id,
                sequence=sequence + 1,
                agent=agent,
                type=kind,
                message=message,
                details=details or {},
            )
        )
        await self.session.commit()

    async def generate(self, agent, data, schema):
        await self.checkpoint()
        self.steps += 1
        if self.steps > settings().max_steps:
            raise ValueError("Maximum agent steps exceeded")
        config = settings()
        context = json.dumps(data)
        if len(context) > config.max_context_chars:
            raise ValueError("Context limit exceeded")
        # Reserve the configured maximum output before issuing a billable request.
        reservation = (
            len(context) * config.input_price_per_million + 4000 * config.output_price_per_million
        ) / 1_000_000
        if self.job.cost + reservation > self.job.budget:
            raise ValueError("Insufficient budget for next model call")
        await self.event(
            agent,
            "agent_started",
            f"{agent.replace('_', ' ').title()} started",
            {"context_chars": len(context), "prompt_version": "v1"},
        )
        result = await llm().complete((PROMPTS / agent / "v1.txt").read_text(), data, schema)
        cost = (
            result.input_tokens * config.input_price_per_million
            + result.output_tokens * config.output_price_per_million
        ) / 1_000_000
        self.session.add(
            Usage(
                organization_id=self.job.organization_id,
                research_id=self.job.id,
                provider=config.llm_provider,
                model=config.llm_model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost=cost,
                latency_ms=result.latency_ms,
                request_id=result.request_id,
            )
        )
        self.job.cost += cost
        await self.session.commit()
        await self.checkpoint()
        await self.event(
            agent,
            "agent_completed",
            f"{agent.replace('_', ' ').title()} completed",
            {
                "latency_ms": result.latency_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "estimated_cost": cost,
            },
        )
        return result.value

    async def tool(self, name):
        await self.checkpoint()
        if self.job.tool_calls >= settings().max_tool_calls:
            raise ValueError("Maximum tool calls exceeded")
        self.job.tool_calls += 1
        await self.event(name, "tool_called", name)

    async def source(self, title, url, evidence, metadata):
        content_hash = digest(evidence)
        existing = await self.session.scalar(
            select(Source).where(Source.research_id == self.job.id, Source.content_hash == content_hash)
        )
        if existing:
            return
        count = await self.session.scalar(select(func.count(Source.id)).where(Source.research_id == self.job.id)) or 0
        source = Source(
            organization_id=self.job.organization_id,
            research_id=self.job.id,
            citation=f"S{count + 1}",
            title=title[:500],
            url=url,
            domain=urlparse(url).hostname or "Uploaded document",
            evidence=evidence[:5000],
            content_hash=content_hash,
            metadata_json=metadata,
        )
        self.session.add(source)
        await self.session.commit()
        await self.event(
            "researcher", "source_found", title[:500], {"citation": source.citation, "source_id": source.id}
        )

    async def collect_web(self, queries):
        query_limit = {"quick": 2, "standard": 3, "deep": 4}[self.job.depth]
        for query in queries[:query_limit]:
            await self.tool("web_search")
            if self.job.cost + settings().search_price_per_call > self.job.budget:
                raise ValueError("Insufficient search budget")
            results = await self.tools.call("web_search", {"query": query}, role="RESEARCHER", approved=True)
            self.job.cost += settings().search_price_per_call
            await self.session.commit()

            # Network I/O is concurrent; evidence persistence remains serialized.
            async def fetch(result):
                try:
                    page = await self.tools.call(
                        "fetch_webpage", {"url": result["url"]}, role="RESEARCHER", approved=True
                    )
                    soup = BeautifulSoup(page, "html.parser")
                    for tag in soup(["script", "style", "nav", "footer"]):
                        tag.decompose()
                    return result, soup.get_text(" ", strip=True)[:5000], None
                except Exception as exc:
                    return result, "", type(exc).__name__

            for result in results:
                await self.tool("fetch_webpage")
            for result, evidence, error in await asyncio.gather(*(fetch(result) for result in results)):
                if error:
                    await self.event(
                        "web_researcher",
                        "source_rejected",
                        "Source could not be safely retrieved",
                        {"error_type": error},
                    )
                elif evidence:
                    await self.source(
                        result["title"],
                        result["url"],
                        evidence,
                        {
                            "retrieved_at": now().isoformat(),
                            "suspicious_content": detect_injection(evidence),
                            "type": "web",
                            "url_validated": True,
                        },
                    )

    async def collect_documents(self):
        await self.tool("document_search")
        for chunk in await self.tools.call(
            "document_search", {"query": self.job.question}, role="RESEARCHER", approved=True
        ):
            document = await self.session.get(Document, chunk.document_id)
            await self.source(
                document.name,
                f"document:{document.id}#page={chunk.page}",
                chunk.text,
                {"page": chunk.page, "chunk_id": chunk.id, "type": "document"},
            )

    async def plan(self):
        if detect_injection(self.job.question):
            raise ValueError("Request contains a prohibited instruction to disclose secrets or bypass controls")
        plan = await self.generate(
            "planner",
            {"question": self.job.question, "source_mode": self.job.source_mode, "depth": self.job.depth},
            Plan,
        )
        self.job.plan = plan.model_dump()
        await self.transition("PLANNING", "WAITING_FOR_APPROVAL")
        await self.event(
            "planner", "approval_required", "Approve the plan, external access and budget to begin research"
        )

    async def execute(self):
        plan = Plan.model_validate(self.job.plan)
        if self.job.source_mode in {"web", "both"}:
            await self.collect_web([task.question for task in plan.tasks])
        if self.job.source_mode in {"documents", "both"}:
            await self.collect_documents()
        sources = list((await self.session.scalars(select(Source).where(Source.research_id == self.job.id))).all())
        evidence = [
            {"citation": source.citation, "title": source.title, "untrusted_evidence": source.evidence[:2000]}
            for source in sources
        ][:10]
        if not evidence:
            raise ValueError("No retrievable evidence; upload indexed documents or check the search configuration")
        analysis = await self.generate("analyst", {"question": self.job.question, "evidence": evidence}, Analysis)
        by_citation = {source.citation: source for source in sources}
        for computation in analysis.computations:
            if len(analysis.findings) >= 30:
                analysis.limitations.append("Additional calculations were omitted to preserve the finding limit.")
                break
            source = by_citation.get(computation.citation)
            quoted_numbers = [
                float(value.replace(",", "")) for value in re.findall(r"-?\d[\d,]*(?:\.\d+)?", computation.quote)
            ]
            if (
                not source
                or not computation.quote
                or computation.quote not in source.evidence
                or any(value not in quoted_numbers for value in computation.values)
            ):
                analysis.limitations.append(
                    "A requested calculation was rejected because its inputs were not grounded in a source quote."
                )
                continue
            await self.tool("calculator")
            result = await registry.call(
                "calculator", {"operation": computation.operation, "values": computation.values}, role="RESEARCHER"
            )
            analysis.findings.append(
                Finding(
                    text=f"Computed {computation.operation} from quoted values {computation.values}: {result['result']:g}. Units and source definitions require review.",
                    kind="ANALYSIS",
                    citations=[computation.citation],
                    quote=computation.quote,
                    status="PARTIALLY_SUPPORTED",
                )
            )
            await self.event("analyst", "tool_completed", "Deterministic calculation completed", result)
        await self.transition("RUNNING", "VERIFICATION")
        assessment = await self.generate(
            "verifier", {"findings": analysis.model_dump(), "evidence": evidence}, Assessment
        )
        if len(assessment.statuses) != len(analysis.findings):
            raise ValueError("Verifier returned an inconsistent finding count")
        for finding, status in zip(analysis.findings, assessment.statuses):
            valid = bool(finding.citations) and all(key in by_citation for key in finding.citations)
            quote_match = bool(finding.quote.strip()) and any(
                finding.quote in by_citation[key].evidence for key in finding.citations if key in by_citation
            )
            finding.status = status if valid and quote_match else "UNSUPPORTED"
            if not valid:
                finding.citations = [key for key in finding.citations if key in by_citation]
        report = await self.generate(
            "writer",
            {"question": self.job.question, "sections": plan.output_sections, "analysis": analysis.model_dump()},
            Report,
        )
        if any(
            index < 0 or index >= len(analysis.findings)
            for section in report.sections
            for index in section.finding_indices
        ):
            raise ValueError("Writer referenced an unknown finding")
        self.job.report = {
            **report.model_dump(),
            "findings": [finding.model_dump() for finding in analysis.findings],
            "sources": [{"citation": s.citation, "title": s.title, "url": s.url} for s in sources],
            "mode": self.job.mode,
        }
        await self.transition("VERIFICATION", "REVIEW")
        await self.event("writer", "approval_required", "Evidence-backed draft ready for final review")

    async def demo(self, planning):
        if planning:
            self.job.plan = {
                "objective": self.job.question,
                "tasks": [
                    {
                        "id": "demo_1",
                        "question": "Inspect the ResearchOS demonstration fixture",
                        "agent": "knowledge_agent",
                    }
                ],
                "output_sections": ["System capabilities"],
            }
            await self.transition("PLANNING", "WAITING_FOR_APPROVAL")
            await self.event("planner", "approval_required", "DEMO fixture plan ready; no external research will run")
        else:
            fixture = "ResearchOS demo fixture: research plans require human approval before execution."
            await self.source("ResearchOS demonstration fixture", "demo:researchos", fixture, {"type": "DEMO"})
            self.job.report = {
                "title": "ResearchOS workflow demonstration",
                "summary": "DEMO: this report describes a local fixture, not real-world research.",
                "sections": [{"title": "System capabilities", "finding_indices": [0]}],
                "limitations": ["Synthetic local fixture; no model or search provider was called."],
                "findings": [
                    {
                        "text": "The demo fixture states that research plans require human approval.",
                        "kind": "FACT",
                        "citations": ["S1"],
                        "quote": fixture,
                        "status": "VERIFIED",
                    }
                ],
                "sources": [{"citation": "S1", "title": "ResearchOS demonstration fixture", "url": "demo:researchos"}],
                "mode": "DEMO",
            }
            await self.transition("RUNNING", "REVIEW")
            await self.event("writer", "approval_required", "DEMO report ready for review")


async def run_research(ctx, research_id: str, planning: bool = True):
    async with Session() as session:
        expected, active = ("QUEUED", "PLANNING") if planning else ("APPROVED", "RUNNING")
        result = await session.execute(
            update(Research).where(Research.id == research_id, Research.status == expected).values(status=active)
        )
        await session.commit()
        if not cast(CursorResult, result).rowcount:
            return
        job = await session.get(Research, research_id)
        if job is None:
            return
        workflow = Workflow(session, job)
        try:
            async with asyncio.timeout(600):
                if job.mode == "DEMO":
                    await workflow.demo(planning)
                elif planning:
                    await workflow.plan()
                else:
                    await workflow.execute()
            await session.commit()
        except Stopped:
            await workflow.event("manager", "research_cancelled", "Research cancelled")
        except Exception as exc:
            await session.rollback()
            await session.refresh(job)
            if job.status != "CANCELLED":
                job.status = "FAILED"
                job.error = (
                    str(exc)[:500]
                    if isinstance(exc, (ValueError, RuntimeError))
                    else f"Execution failed: {type(exc).__name__}"
                )
            await workflow.event("manager", "research_failed", job.error or "Cancelled")
