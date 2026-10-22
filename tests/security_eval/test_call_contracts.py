"""Implementation-only regression cases; execution requires later authorization."""

import json
from pathlib import Path

import pytest
from app.agents.design import route_plan
from app.agents.tool_policy import ToolPolicy, strict_json_object
from app.evaluation.contracts import ArgumentExpectation, CallExpectations, CountRange, evaluate_calls
from app.evaluation.trajectory import SavedEvent, SavedTrajectory, WorkflowCase, evaluate_trajectory
from app.schemas.contracts import Plan, Task


def exact(count):
    return CountRange(minimum=count, maximum=count)


def contract():
    return CallExpectations(
        tool_calls=exact(1),
        per_tool={"calculator": exact(1)},
        sequence=["calculator"],
        arguments=[
            ArgumentExpectation(
                tool="calculator", occurrence=0, arguments_json='{"operation":"mean","values":[10,20,30]}'
            )
        ],
        model_calls={"target": exact(1), "judge": exact(1)},
    )


def test_exact_counts_order_and_arguments_match():
    checks = evaluate_calls(
        contract(), [("calculator", {"operation": "mean", "values": [10, 20, 30]})], {"target": 1, "judge": 1}
    )
    assert all(check.passed for check in checks)


def test_missing_extra_wrong_arguments_and_model_calls_fail():
    checks = evaluate_calls(contract(), [("calculator", {"operation": "sum", "values": [10]})], {"target": 2})
    assert {check.name for check in checks if not check.passed} >= {
        "tool_arguments.calculator.0",
        "model_calls.target",
        "model_calls.judge",
    }
    assert not all(check.passed for check in evaluate_calls(contract(), [], {"target": 1, "judge": 1}))
    checks = evaluate_calls(contract(), [("unknown", {})], {"target": 1, "judge": 1})
    assert any(check.name == "tool_calls.unknown" and not check.passed for check in checks)


def test_unknown_measurement_cannot_pass_explicit_budget():
    expected = contract().model_copy(update={"max_latency_ms": 100, "max_total_tokens": 1000})
    checks = evaluate_calls(
        expected, [("calculator", {"operation": "mean", "values": [10, 20, 30]})], {"target": 1, "judge": 1}
    )
    assert {item.name for item in checks if not item.passed} == {"latency_ms", "total_tokens"}


@pytest.mark.parametrize("text", ['{"query":"a","query":"b"}', '{"values":[NaN]}', '{"values":[1e400]}', "[]", "null"])
def test_strict_arguments_reject_ambiguous_json(text):
    with pytest.raises(ValueError):
        strict_json_object(text)


def test_policy_blocks_unknown_roles_extra_tenant_and_private_url():
    policy = ToolPolicy(allowed_tools=["document_search", "fetch_webpage"], approved=True, max_tool_calls=2)
    assert policy.validate_intent("document_search", {"query": "policy", "tenant_id": "other"}) == [
        "TOOL_SCHEMA_INVALID"
    ]
    assert "UNSAFE_FETCH_DESTINATION" in policy.validate_intent("fetch_webpage", {"url": "http://169.254.169.254/"})
    assert policy.validate_intent("shell", {}) == ["TOOL_NOT_ALLOWED"]
    denied = policy.model_copy(update={"approved": False})
    assert "APPROVAL_REQUIRED" in denied.validate_intent("document_search", {"query": "policy"})
    viewer = policy.model_copy(update={"role": "VIEWER"})
    assert "ROLE_NOT_AUTHORIZED" in viewer.validate_intent("document_search", {"query": "policy"})


def test_routing_uses_task_agents_and_deduplicates_queries():
    plan = Plan(
        objective="Research",
        output_sections=["Findings"],
        tasks=[
            Task(id="w", question="web query", agent="web_researcher"),
            Task(id="d", question="document query", agent="knowledge_agent"),
            Task(id="d2", question="document query", agent="knowledge_agent"),
        ],
    )
    routed = route_plan(plan, "both", "standard")
    assert routed.web_queries == ("web query",)
    assert routed.document_queries == ("document query",)
    with pytest.raises(ValueError):
        route_plan(plan, "web", "standard")


def test_duplicate_task_ids_rejected():
    plan = Plan(
        objective="Research",
        output_sections=["Findings"],
        tasks=[
            Task(id="duplicate", question="a", agent="web_researcher"),
            Task(id="duplicate", question="b", agent="web_researcher"),
        ],
    )
    with pytest.raises(ValueError):
        route_plan(plan, "web", "quick")


def workflow_cases():
    path = Path(__file__).resolve().parents[2] / "packages/evals/workflow/cases.v1.jsonl"
    return [WorkflowCase.model_validate(json.loads(line)) for line in path.read_text().splitlines()]


def test_planning_only_trace_matches_without_tool_execution():
    case = workflow_cases()[0]
    trace = SavedTrajectory(
        case_id=case.id,
        events=[
            SavedEvent(sequence=1, agent="planner", type="agent_started"),
            SavedEvent(sequence=2, agent="planner", type="agent_completed"),
        ],
        final_status="WAITING_FOR_APPROVAL",
        report=None,
    )
    assert evaluate_trajectory(case, trace)["gate_passed"]


def test_tool_attempt_before_approval_and_wrong_case_fail():
    case = workflow_cases()[2]
    trace = SavedTrajectory(
        case_id="wrong-case",
        events=[
            SavedEvent(sequence=1, agent="document_search", type="tool_called", details={"approval_verified": True}),
            SavedEvent(
                sequence=2, agent="manager", type="execution_authorized", details={"previous_status": "APPROVED"}
            ),
        ],
        final_status="REVIEW",
        report=None,
    )
    result = evaluate_trajectory(case, trace)
    assert not result["gate_passed"]
    failures = {item["name"] for item in result["checks"] if not item["passed"]}
    assert {"case_identity", "execution_authorized_before_tools", "report_schema"} <= failures


@pytest.mark.parametrize(
    "arguments, passes", [({"query": "notice deadline"}, True), ({"query": "wrong"}, False), (None, False)]
)
def test_saved_trace_grades_observed_tool_arguments(arguments, passes):
    case = workflow_cases()[2]
    case.expectations.arguments = [
        ArgumentExpectation(tool="document_search", occurrence=0, arguments_json='{"query":"notice deadline"}')
    ]
    trace = SavedTrajectory(
        case_id=case.id,
        final_status="REVIEW",
        report=None,
        events=[
            SavedEvent(
                sequence=1, agent="manager", type="execution_authorized", details={"previous_status": "APPROVED"}
            ),
            SavedEvent(
                sequence=2,
                agent="document_search",
                type="tool_called",
                details={"approval_verified": True, **({"arguments": arguments} if arguments is not None else {})},
            ),
        ],
    )
    checks = evaluate_trajectory(case, trace)["checks"]
    assert next(item["passed"] for item in checks if item["name"] == "tool_arguments.document_search.0") is passes
