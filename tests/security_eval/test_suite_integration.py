"""Full shipped eval-set integration with labeled structured provider fixtures."""

from pathlib import Path

from app.evaluation.security import (
    AgentResponse,
    JudgeResponse,
    Judgment,
    SecurityEvaluator,
    ToolIntent,
    load_cases,
    summarize,
)
from app.services.providers import Completion, LLMProvider


class ScenarioProvider(LLMProvider):
    def __init__(self, case):
        self.case = case
        self.calls = 0

    async def complete(self, system, data, schema):
        self.calls += 1
        if schema is AgentResponse:
            assert "APPLICATION TOOL POLICY" in system
            assert "expectations" not in data
            intents = []
            for name in self.case.expectations.sequence:
                occurrence = sum(intent.name == name for intent in intents)
                exact = next(
                    (
                        item.arguments_json
                        for item in self.case.expectations.arguments
                        if item.tool == name and item.occurrence == occurrence
                    ),
                    None,
                )
                arguments = exact or '{"query":"research approval"}'
                intents.append(ToolIntent(name=name, arguments_json=arguments))
            response = AgentResponse(answer="Synthetic safe response; no tools executed.", tool_intents=intents)
        else:
            assert schema is JudgeResponse
            response = JudgeResponse(
                judgments=[
                    Judgment(
                        check_id=check.id, verdict="PASS", evidence_quote="", explanation="Injected grading fixture"
                    )
                    for check in self.case.checks
                ]
            )
        return Completion(response, 10, 5, 1, "synthetic-eval-request", http_attempts=1)


async def test_complete_shipped_suite_preserves_manifest_and_call_counts():
    root = Path(__file__).resolve().parents[2]
    cases = load_cases(root / "packages/evals/security/cases.v1.jsonl")
    results = []
    for case in cases:
        provider = ScenarioProvider(case)
        results.append(await SecurityEvaluator(provider, provider, "Reference test policy").evaluate(case))
        assert provider.calls == 2
    manifest = {(case.id, 1) for case in cases}
    summary = summarize(results, len(cases), manifest)
    assert summary["gate_passed"]
    assert summary["logical_model_calls"] == summary["http_attempts"] == 44
    assert summary["proposed_tool_calls"] == 7
    assert summary["dispatched_tool_calls"] == summary["contract_failures"] == 0
    assert not summarize(results[:-1], len(cases), manifest)["gate_passed"]
    assert not summarize(results, len(cases), {(case.id, 2) for case in cases})["gate_passed"]
