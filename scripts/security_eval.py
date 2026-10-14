"""Explicit opt-in live LLM evaluation; does not run application tools or Docker."""

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.core.config import settings  # noqa: E402
from app.evaluation.security import PROMPT_ROOT, SecurityEvaluator, load_cases, suite_plan, summarize  # noqa: E402
from app.services.providers import llm  # noqa: E402


async def run(args):
    cases = load_cases(args.dataset)
    target_prompt = args.target_prompt.read_text(encoding="utf-8-sig")
    plan = suite_plan(cases, args.repetitions)
    expected = len(cases) * args.repetitions
    if expected * 2 > args.max_model_calls:
        raise ValueError("Two model calls per case exceed --max-model-calls")
    if not args.live:
        print(
            json.dumps(
                {
                    "mode": "DRY_RUN",
                    **plan,
                    "tools_executed": False,
                    "case_contracts": [
                        {"case_id": case.id, "expectations": case.expectations.model_dump()} for case in cases
                    ],
                },
                indent=2,
            )
        )
        return 0
    provider = llm()
    evaluator = SecurityEvaluator(provider, provider, target_prompt, args.timeout_seconds)
    results = []
    started = datetime.now(UTC).isoformat()
    for repetition in range(1, args.repetitions + 1):
        for case in cases:
            results.append(await evaluator.evaluate(case, repetition))
    report = {
        "schema_version": "2",
        "mode": "LIVE_LLM_TOOL_INTENT_EVAL",
        "started_at": started,
        "run_plan": plan,
        "finished_at": datetime.now(UTC).isoformat(),
        "provider": settings().llm_provider,
        "model": settings().llm_model,
        "judge_uses_same_model": True,
        "tools_executed": False,
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "target_prompt_sha256": hashlib.sha256(target_prompt.encode()).hexdigest(),
        "judge_prompt_sha256": hashlib.sha256((PROMPT_ROOT / "judge.v1.txt").read_bytes()).hexdigest(),
        "summary": summarize(
            results,
            expected,
            {(case.id, repetition) for case in cases for repetition in range(1, args.repetitions + 1)},
        ),
        "case_contracts": [{"case_id": case.id, "expectations": case.expectations.model_dump()} for case in cases],
        "results": [item.model_dump() for item in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental overwriting of an earlier evaluation.
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report["summary"], indent=2))
    return 0 if report["summary"]["gate_passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly allow billable model calls")
    parser.add_argument("--dataset", type=Path, default=ROOT / "packages/evals/security/cases.smoke.jsonl")
    parser.add_argument("--target-prompt", type=Path, default=PROMPT_ROOT / "target.v1.txt")
    parser.add_argument("--repetitions", type=int, choices=range(1, 11), default=1)
    parser.add_argument("--max-model-calls", type=int, default=100)
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument("--output", type=Path, default=ROOT / "security-eval-results/report.json")
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 300 or args.max_model_calls < 1:
        parser.error("Timeout must be 1–300 seconds and max-model-calls must be positive")
    if args.live and args.output.exists():
        parser.error("Output already exists; select a new --output path")
    try:
        return asyncio.run(run(args))
    except (ValueError, OSError):
        print("Evaluation configuration or output error; no result should be treated as passing.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
