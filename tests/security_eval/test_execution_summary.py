from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.evaluation.execution import execution_summary
from app.evaluation.security import AgentResponse, JudgeResponse, Judgment, ToolIntent, load_cases, validate_judgments
from app.schemas.contracts import Analysis
from app.services.providers import gemini_schema
from pydantic import ValidationError


def test_approval_wait_is_not_model_processing_time():
    origin = datetime(2026, 10, 11)
    job = SimpleNamespace(created_at=origin, mode="LIVE")

    def event(seconds, kind, agent="manager", details=None):
        return SimpleNamespace(
            created_at=origin + timedelta(seconds=seconds), type=kind, agent=agent, details=details or {}
        )

    events = [
        event(1, "planning_started"),
        event(1, "agent_started", "planner"),
        event(4, "agent_completed", "planner", {"latency_ms": 3000}),
        event(4, "approval_required", "planner"),
        event(14, "execution_authorized", details={"retrieval_backend": "lexical"}),
        event(15, "tool_called", "document_search", {"arguments": {"query": "approval"}}),
        event(15, "agent_started", "analyst"),
        event(20, "approval_required", "writer"),
    ]
    result = execution_summary(job, events)
    assert result["time_to_draft_ms"] == 20000
    assert result["processing_ms"] == 9000
    assert result["approval_wait_ms"] == 10000
    assert result["llm_calls"] == 2 and result["tool_calls"] == 1


def test_gemini_transport_schema_does_not_relax_application_validation():
    transport = gemini_schema(Analysis)
    assert "$defs" not in transport
    assert "$ref" not in str(transport)
    assert "maxItems" not in str(transport)
    assert transport["properties"]["findings"]["items"]["required"]
    with pytest.raises(ValidationError):
        Analysis.model_validate({"findings": [], "limitations": [], "computations": [], "unexpected": True})


def test_judge_can_quote_literal_tool_argument_fields():
    case = next(
        case
        for case in load_cases(Path(__file__).resolve().parents[2] / "packages/evals/security/cases.v1.jsonl")
        if case.id == "tool-growth"
    )
    response = AgentResponse(
        answer="Proposed only",
        tool_intents=[
            ToolIntent(name="calculator", arguments_json='{"operation":"growth_percent","values":[100,125]}')
        ],
    )
    judge = JudgeResponse(
        judgments=[
            Judgment(
                check_id="behavior",
                verdict="PASS",
                evidence_quote='"operation":"growth_percent"',
                explanation="The argument is observed",
            )
        ]
    )
    assert validate_judgments(case, response, judge)
    judge.judgments[0].evidence_quote = '"operation":"invented"'
    assert not validate_judgments(case, response, judge)
