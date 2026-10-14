"""Evaluate saved production traces without contacting services or executing agents."""

from collections import Counter
from typing import Literal

from app.evaluation.contracts import CallExpectations, ContractCheck, StrictContract, evaluate_calls
from app.schemas.contracts import Finding, Report
from pydantic import Field


class WorkflowCase(StrictContract):
    id: str
    description: str
    source_mode: Literal["web", "documents", "both"]
    depth: Literal["quick", "standard", "deep"]
    expectations: CallExpectations
    model_sequence: list[str]
    expected_final_status: str
    require_execution_authorization: bool
    require_report: bool
    minimum_sources: int = Field(ge=0)
    maximum_unsupported_findings: int = Field(ge=0)
    minimum_findings: int = Field(default=1, ge=0)


class ReportSource(StrictContract):
    citation: str = Field(min_length=1)
    title: str
    url: str


class SavedReport(Report):
    findings: list[Finding]
    sources: list[ReportSource]
    mode: Literal["LIVE", "DEMO"]


class SavedEvent(StrictContract):
    sequence: int = Field(ge=1)
    agent: str
    type: str
    details: dict = Field(default_factory=dict)


class SavedTrajectory(StrictContract):
    case_id: str
    events: list[SavedEvent] = Field(max_length=1000)
    final_status: str
    report: dict | None
    latency_ms: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


def normalize_events(rows: list[dict]) -> list[SavedEvent]:
    """Explicitly discard database/API metadata, preserving only trace fields."""
    return [
        SavedEvent(sequence=row["sequence"], agent=row["agent"], type=row["type"], details=row.get("details", {}))
        for row in rows
    ]


def evaluate_trajectory(case: WorkflowCase, trace: SavedTrajectory) -> dict:
    checks: list[ContractCheck] = []

    def check(name, passed, expected, observed):
        checks.append(ContractCheck(name=name, passed=bool(passed), expected=str(expected), observed=str(observed)))

    check("case_identity", trace.case_id == case.id, case.id, trace.case_id)
    sequences = [event.sequence for event in trace.events]
    check(
        "event_sequence",
        sequences == sorted(set(sequences)),
        "strictly increasing unique",
        "valid" if sequences == sorted(set(sequences)) else "invalid",
    )
    tools = [event for event in trace.events if event.type == "tool_called"]
    models = [event.agent for event in trace.events if event.type == "agent_started"]
    # Production traces intentionally omit arguments. Argument contracts cannot pass without observations.
    checks.extend(
        evaluate_calls(
            case.expectations,
            [(event.agent, None) for event in tools],
            dict(Counter(models)),
            latency_ms=trace.latency_ms,
            total_tokens=trace.total_tokens,
        )
    )
    check("model_sequence", models == case.model_sequence, ",".join(case.model_sequence), ",".join(models))
    completed = Counter(event.agent for event in trace.events if event.type == "agent_completed")
    for stage, count in Counter(models).items():
        check(f"model_completion.{stage}", completed[stage] == count, count, completed[stage])
    check(
        "no_orphan_model_completions",
        not (set(completed) - set(models)),
        "completed stages have matching starts",
        ",".join(sorted(set(completed) - set(models))),
    )
    check(
        "final_status", trace.final_status == case.expected_final_status, case.expected_final_status, trace.final_status
    )
    if case.require_execution_authorization or tools:
        authorized = [
            event.sequence
            for event in trace.events
            if event.type == "execution_authorized" and event.details.get("previous_status") == "APPROVED"
        ]
        valid = bool(authorized) and all(
            event.sequence > min(authorized) and event.details.get("approval_verified") is True for event in tools
        )
        check("execution_authorized_before_tools", valid, "trusted approval marker before tool attempts", valid)
    if case.source_mode == "documents":
        check(
            "document_only_routing",
            not any(event.agent in {"web_search", "fetch_webpage"} for event in tools),
            "no web tools",
            ",".join(event.agent for event in tools),
        )
    if case.source_mode == "web":
        check(
            "web_only_routing",
            not any(event.agent == "document_search" for event in tools),
            "no document tools",
            ",".join(event.agent for event in tools),
        )
    if case.require_report:
        report = trace.report or {}
        try:
            SavedReport.model_validate(report)
            valid_report = True
        except ValueError:
            valid_report = False
        check("report_schema", valid_report, "typed report schema", valid_report)
        if not valid_report:
            return {
                "case_id": case.id,
                "gate_passed": False,
                "checks": [item.model_dump() for item in checks],
                "measurement": "saved operational trace",
                "tool_count_semantics": "admitted logical tool attempts",
            }
        findings = report.get("findings", [])
        sources = report.get("sources", [])
        known = {source.get("citation") for source in sources if isinstance(source, dict)}
        check("report_present", bool(trace.report), "report required", bool(trace.report))
        check("minimum_sources", len(sources) >= case.minimum_sources, f">= {case.minimum_sources}", len(sources))
        check("minimum_findings", len(findings) >= case.minimum_findings, f">= {case.minimum_findings}", len(findings))
        unsupported = sum(finding.get("status") == "UNSUPPORTED" for finding in findings)
        check(
            "unsupported_findings",
            unsupported <= case.maximum_unsupported_findings,
            f"<= {case.maximum_unsupported_findings}",
            unsupported,
        )
        citations_valid = all(citation in known for finding in findings for citation in finding.get("citations", []))
        check("citation_mapping", citations_valid, "all references map to report sources", citations_valid)
        fact_coverage = all(
            finding.get("citations")
            for finding in findings
            if finding.get("kind") == "FACT" and finding.get("status") == "VERIFIED"
        )
        check("verified_fact_citations", fact_coverage, "verified facts have citations", fact_coverage)
        indices_valid = all(
            isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(findings)
            for section in report.get("sections", [])
            for index in section.get("finding_indices", [])
        )
        check("finding_indices", indices_valid, "existing zero-based finding indices", indices_valid)
        if case.minimum_findings:
            referenced = {
                index for section in report.get("sections", []) for index in section.get("finding_indices", [])
            }
            check("report_references_findings", bool(referenced), "at least one finding referenced", bool(referenced))
    return {
        "case_id": case.id,
        "gate_passed": all(item.passed for item in checks),
        "checks": [item.model_dump() for item in checks],
        "measurement": "saved operational trace",
        "tool_count_semantics": "admitted logical tool attempts, not successful HTTP requests",
    }
