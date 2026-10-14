"""Observed execution summaries from persisted events; no inferred tool results."""

from collections import Counter


def execution_summary(job, events):
    def first(kind, agent=None):
        return next((event for event in events if event.type == kind and (agent is None or event.agent == agent)), None)

    def elapsed(start, end):
        return max(0, round((end - start).total_seconds() * 1000)) if start and end else None

    planning = first("planning_started") or first("agent_started", "planner")
    plan_ready = first("approval_required", "planner")
    execution = first("execution_authorized")
    draft = first("approval_required", "writer")
    planning_ms = elapsed(planning.created_at if planning else None, plan_ready.created_at if plan_ready else None)
    execution_ms = elapsed(execution.created_at if execution else None, draft.created_at if draft else None)
    completed = [event for event in events if event.type == "agent_completed"]
    calls = [event for event in events if event.type == "agent_started"]
    tools = [event for event in events if event.type == "tool_called"]
    return {
        "mode": job.mode,
        "retrieval_backend": next(
            (event.details.get("retrieval_backend") for event in events if event.type == "execution_authorized"), None
        ),
        "time_to_draft_ms": elapsed(job.created_at, draft.created_at if draft else None),
        "processing_ms": planning_ms + execution_ms if planning_ms is not None and execution_ms is not None else None,
        "planning_ms": planning_ms,
        "execution_ms": execution_ms,
        "approval_wait_ms": elapsed(
            plan_ready.created_at if plan_ready else None, execution.created_at if execution else None
        ),
        "llm_calls": len(calls),
        "tool_calls": len(tools),
        "tools_by_name": dict(Counter(event.agent for event in tools)),
        "model_calls": [{"agent": event.agent, **event.details} for event in completed],
        "tool_activity": [
            {
                "name": event.agent,
                **event.details,
                "arguments": {
                    key: value
                    for key, value in event.details.get("arguments", {}).items()
                    if key != "retrieval_backend"
                },
            }
            for event in tools
        ],
    }
