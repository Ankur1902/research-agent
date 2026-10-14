"""Deterministic research routing and execution boundaries."""

from dataclasses import dataclass
from typing import Literal

from app.schemas.contracts import Plan

MODEL_STAGES = ("planner", "analyst", "verifier", "writer")
DEPTH_QUERY_LIMITS = {"quick": 2, "standard": 3, "deep": 4}


@dataclass(frozen=True)
class RetrievalPlan:
    web_queries: tuple[str, ...]
    document_queries: tuple[str, ...]


def route_plan(plan: Plan, source_mode: Literal["web", "documents", "both"], depth: str) -> RetrievalPlan:
    if depth not in DEPTH_QUERY_LIMITS:
        raise ValueError("Unknown research depth")
    allowed = {
        "web": {"web_researcher"},
        "documents": {"knowledge_agent"},
        "both": {"web_researcher", "knowledge_agent"},
    }[source_mode]
    if len({task.id for task in plan.tasks}) != len(plan.tasks):
        raise ValueError("Plan task IDs must be unique")
    if any(task.agent not in allowed or not task.question.strip() for task in plan.tasks):
        raise ValueError("Plan violates source mode or contains an empty task")
    limit = DEPTH_QUERY_LIMITS[depth]

    def queries(agent):
        # Stable deduplication prevents identical tasks from spending multiple tool calls.
        return tuple(dict.fromkeys(task.question.strip() for task in plan.tasks if task.agent == agent))[:limit]

    return RetrievalPlan(queries("web_researcher"), queries("knowledge_agent"))
