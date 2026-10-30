import asyncio
import json
import re
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

from app.agents.design import DEPTH_QUERY_LIMITS, MODEL_STAGES, route_plan
from app.agents.evidence import pack_evidence
from app.core.config import settings
from app.core.db import Session
from app.core.telemetry import annotate, mark_failed, span, trace_ref
from app.models.entities import Document, Event, Research, RunLease, Source, Usage, now
from app.rag.pipeline import retrieve
from app.schemas.contracts import Analysis, Assessment, Finding, Plan, Report
from app.security.guards import detect_injection, digest, redact_secrets
from app.services.budgets import reserve, settle
from app.services.providers import ProviderUnavailable, RequestRejected, StructuredResponseError, llm
from app.tools.registry import registry
from app.tools.research import research_tools
from bs4 import BeautifulSoup
from sqlalchemy import CursorResult, func, select, update

PROMPTS = Path(__file__).resolve().parents[4] / "packages" / "prompts"


# OpenTelemetry GenAI semantic-convention provider names.
GEN_AI_PROVIDER = {"openai": "openai", "anthropic": "anthropic", "gemini": "gcp.gemini"}


class Stopped(Exception):
    pass


class Workflow:
    def __init__(self, session, job):
        self.session, self.job = session, job
        self.tools = research_tools(lambda query: retrieve(self.session, self.job.organization_id, query))

    async def checkpoint(self):
        await self.session.refresh(self.job)
        lease = await self.session.get(RunLease, self.job.id, populate_existing=True)
        if self.job.status in {"CANCELLED", "FAILED"} or (lease and lease.expires_at <= now()):
            raise Stopped()
        if self.job.cost > self.job.budget:
            raise ValueError("Research budget exhausted")

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
        attributes = {"gen_ai.operation.name": "chat", "researchos.agent": agent, "researchos.research_id": self.job.id}
        with span(f"agent.{agent}", attributes):
            return await self._generate(agent, data, schema)

    async def _generate(self, agent, data, schema):
        await self.checkpoint()
        if agent not in MODEL_STAGES:
            raise ValueError("Unknown model stage")
        prior_calls = (
            await self.session.scalar(
                select(func.count(Event.id)).where(Event.research_id == self.job.id, Event.type == "agent_started")
            )
            or 0
        )
        if prior_calls >= settings().max_steps:
            raise ValueError("Maximum agent steps exceeded")
        config = settings()
        context = json.dumps(data)
        if len(context) > config.max_context_chars:
            raise ValueError("Context limit exceeded")
        prompt = (PROMPTS / agent / "v1.txt").read_text(encoding="utf-8-sig")
        # UTF-8 byte count is a conservative token estimate, including instructions,
        # schema, and protocol overhead. Reservations are admission estimates, not invoices.
        input_bound = len((prompt + context + json.dumps(schema.model_json_schema())).encode("utf-8")) + 1024
        input_price, output_price = config.price_ceiling()  # cover whichever chain member ends up serving
        reservation = (input_bound * input_price + 4000 * output_price) / 1_000_000
        receipt = await reserve(self.session, self.job, reservation, "model")
        annotate(
            {
                "researchos.prompt_sha256": digest(prompt),
                "researchos.logical_call_number": prior_calls + 1,
                "researchos.reserved_usd": reservation,
                "gen_ai.request.model": config.llm_model,
            }
        )
        await self.event(
            agent,
            "agent_started",
            f"{agent.replace('_', ' ').title()} started",
            {
                "context_chars": len(context),
                "prompt_version": "v1",
                "prompt_sha256": digest(prompt),
                "logical_call_number": prior_calls + 1,
                "provider": config.llm_provider,
                "model": config.llm_model,
                "reservation_id": receipt.id,
                "reserved_cost": reservation,
            },
        )
        validation_error = None
        try:
            result = await llm().complete(prompt, data, schema)
        except (RequestRejected, ProviderUnavailable):
            # Provably unprocessed (declined, unreachable, throttled, or every circuit open): release the hold.
            await settle(self.session, self.job, receipt, 0)
            raise
        except StructuredResponseError as exc:
            result, validation_error = exc.receipt, exc
        provider, model = result.provider or config.llm_provider, result.model or config.llm_model
        input_price, output_price = config.price_for(provider, model)
        cost = (result.input_tokens * input_price + result.output_tokens * output_price) / 1_000_000
        annotate(
            {
                "gen_ai.provider.name": GEN_AI_PROVIDER.get(provider, provider),
                "gen_ai.response.model": model,
                "gen_ai.response.id": result.request_id,
                "gen_ai.usage.input_tokens": result.input_tokens,
                "gen_ai.usage.output_tokens": result.output_tokens,
                "researchos.cost.estimated_usd": cost,
                "researchos.latency_ms": result.latency_ms,
                "researchos.http_attempts": result.http_attempts,
                "researchos.failover_skipped": len(result.failover or []),
            }
        )
        self.session.add(
            Usage(
                organization_id=self.job.organization_id,
                research_id=self.job.id,
                provider=provider,
                model=model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost=cost,
                latency_ms=result.latency_ms,
                request_id=result.request_id,
            )
        )
        await settle(self.session, self.job, receipt, cost)
        if validation_error:
            await self.event(
                agent,
                "agent_response_rejected",
                "Structured response failed validation; usage recorded",
                {"reservation_id": receipt.id, "estimated_cost": cost},
            )
            raise validation_error
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
                "provider": provider,
                "model": model,
                "http_attempts": result.http_attempts,
                **({"failover": result.failover} if result.failover else {}),
            },
        )
        return result.value

    async def tool(self, name, arguments=None):
        await self.checkpoint()
        if self.job.status != "RUNNING":
            raise PermissionError("Retrieval and calculations require the approved execution phase")
        if self.job.tool_calls >= settings().max_tool_calls:
            raise ValueError("Maximum tool calls exceeded")
        self.job.tool_calls += 1
        await self.event(
            name,
            "tool_called",
            name,
            {
                "call_number": self.job.tool_calls,
                "approval_verified": True,
                "phase": self.job.status,
                "arguments": arguments or {},
            },
        )

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
        query_limit = DEPTH_QUERY_LIMITS[self.job.depth]
        for query in queries[:query_limit]:
            receipt = await reserve(self.session, self.job, settings().search_price_per_call, "search")
            await self.tool("web_search", {"query": query})
            try:
                with span("tool.web_search", {"researchos.tool.call_number": self.job.tool_calls}):
                    results = (
                        await self.tools.call("web_search", {"query": query}, role="RESEARCHER", approved=True)
                    )[:4]
                    annotate({"researchos.result_count": len(results)})
            except (RequestRejected, ValueError):
                # Declined before any search was performed: release the hold instead of leaking budget.
                await settle(self.session, self.job, receipt, 0)
                raise
            results = list({result["url"]: result for result in results}.values())
            await settle(self.session, self.job, receipt, settings().search_price_per_call)

            # Network I/O is concurrent; evidence persistence remains serialized.
            async def fetch(result):
                try:
                    with span("tool.fetch_webpage"):
                        page = await self.tools.call(
                            "fetch_webpage", {"url": result["url"]}, role="RESEARCHER", approved=True
                        )
                        annotate({"researchos.response_chars": len(page)})
                    soup = BeautifulSoup(page, "html.parser")
                    for tag in soup(["script", "style", "nav", "footer"]):
                        tag.decompose()
                    return result, soup.get_text(" ", strip=True)[:5000], None
                except Exception as exc:
                    return result, "", type(exc).__name__

            if self.job.tool_calls + len(results) > settings().max_tool_calls:
                raise ValueError("Insufficient tool-call budget for fetch batch")
            for result in results:
                await self.tool("fetch_webpage", {"url": result["url"]})
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

    async def collect_documents(self, queries):
        for query in queries:
            await self.tool("document_search", {"query": query})
            with span("tool.document_search"):
                chunks = await self.tools.call("document_search", {"query": query}, role="RESEARCHER", approved=True)
                annotate({"researchos.result_count": len(chunks)})
            for chunk in chunks:
                document = await self.session.get(Document, chunk.document_id)
                if document is None or document.organization_id != self.job.organization_id:
                    raise PermissionError("Retrieved document does not belong to the active organization")
                await self.source(
                    document.name,
                    f"document:{document.id}#page={chunk.page}",
                    chunk.text,
                    {
                        "page": chunk.page,
                        "chunk_id": chunk.id,
                        "type": "document",
                        "suspicious_content": detect_injection(chunk.text),
                    },
                )

    async def plan(self):
        if detect_injection(self.job.question):
            raise ValueError("Request contains a prohibited instruction to disclose secrets or bypass controls")
        plan = await self.generate(
            "planner",
            {"question": self.job.question, "source_mode": self.job.source_mode, "depth": self.job.depth},
            Plan,
        )
        route_plan(plan, self.job.source_mode, self.job.depth)
        self.job.plan = plan.model_dump()
        await self.transition("PLANNING", "WAITING_FOR_APPROVAL")
        await self.event(
            "planner", "approval_required", "Approve the plan, external access and budget to begin research"
        )

    async def execute(self):
        plan = Plan.model_validate(self.job.plan)
        routing = route_plan(plan, self.job.source_mode, self.job.depth)
        if routing.web_queries:
            with span("research.collect_web", {"researchos.query_count": len(routing.web_queries)}):
                await self.collect_web(routing.web_queries)
        if routing.document_queries:
            with span("research.collect_documents", {"researchos.query_count": len(routing.document_queries)}):
                await self.collect_documents(routing.document_queries)
        sources = list((await self.session.scalars(select(Source).where(Source.research_id == self.job.id))).all())
        evidence = pack_evidence(sources, self.job.question)
        if not evidence:
            raise ValueError("No retrievable evidence; upload indexed documents or check the search configuration")
        analysis = await self.generate("analyst", {"question": self.job.question, "evidence": evidence}, Analysis)
        if any(item["possible_embedded_instructions"] for item in evidence):
            analysis.limitations.append(
                "Some sources contained instruction-like text; it was treated as data and never followed."
            )
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
                or any(count > Counter(quoted_numbers)[value] for value, count in Counter(computation.values).items())
            ):
                analysis.limitations.append(
                    "A requested calculation was rejected because its inputs were not grounded in a source quote."
                )
                continue
            await self.tool("calculator", {"operation": computation.operation, "values": computation.values})
            with span("tool.calculator", {"researchos.operation": computation.operation}):
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
        # Output guardrail: credential-shaped strings never reach storage or exports.
        self.job.report = redact_secrets(
            {
                **report.model_dump(),
                "findings": [finding.model_dump() for finding in analysis.findings],
                "sources": [{"citation": s.citation, "title": s.title, "url": s.url} for s in sources],
                "mode": self.job.mode,
            }
        )
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
    phase = "planning" if planning else "execution"
    with span("research.run", {"researchos.research_id": research_id, "researchos.phase": phase}):
        await _run_research(research_id, planning)


async def _run_research(research_id: str, planning: bool):
    async with Session() as session:
        expected, active = ("QUEUED", "PLANNING") if planning else ("APPROVED", "RUNNING")
        result = await session.execute(
            update(Research).where(Research.id == research_id, Research.status == expected).values(status=active)
        )
        if not cast(CursorResult, result).rowcount:
            await session.rollback()
            return
        # Never replay an interrupted phase across an uncertain paid call.
        await session.merge(RunLease(research_id=research_id, expires_at=now() + timedelta(seconds=720)))
        await session.commit()
        job = await session.get(Research, research_id)
        if job is None:
            return
        workflow = Workflow(session, job)
        annotate(
            {
                "researchos.organization_id": job.organization_id,
                "researchos.mode": job.mode,
                "researchos.depth": job.depth,
                "researchos.source_mode": job.source_mode,
            }
        )
        try:
            async with asyncio.timeout(600):
                if not planning:
                    await workflow.event(
                        "manager",
                        "execution_authorized",
                        "Approved research execution started",
                        {
                            "previous_status": "APPROVED",
                            "mode": job.mode,
                            "retrieval_backend": settings().retrieval_backend,
                            **trace_ref(),
                        },
                    )
                else:
                    await workflow.event("manager", "planning_started", "Research planning started", trace_ref() or None)
                if job.mode == "DEMO":
                    await workflow.demo(planning)
                elif planning:
                    await workflow.plan()
                else:
                    await workflow.execute()
            await session.commit()
            annotate({"researchos.status_after": job.status})
        except Stopped:
            annotate({"researchos.outcome": "stopped"})
            await workflow.event("manager", "research_stopped", "Research stopped by cancellation or execution deadline")
        except Exception as exc:
            mark_failed(exc)
            annotate({"researchos.outcome": "failed"})
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
