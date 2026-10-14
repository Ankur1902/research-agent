"""Offline saved-trace evaluation. No provider, Docker, or database access."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))

from app.evaluation.trajectory import SavedTrajectory, WorkflowCase, evaluate_trajectory  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "packages/evals/workflow/cases.v1.jsonl")
    parser.add_argument("--trace", type=Path, required=True, help="Saved normalized trajectory JSON")
    args = parser.parse_args()
    try:
        if args.dataset.stat().st_size > 2_000_000 or args.trace.stat().st_size > 2_000_000:
            raise ValueError("Input exceeds limit")
        cases = [
            WorkflowCase.model_validate_json(line)
            for line in args.dataset.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not cases or len(cases) > 500 or len({case.id for case in cases}) != len(cases):
            raise ValueError("Invalid dataset manifest")
        trace = SavedTrajectory.model_validate_json(args.trace.read_text(encoding="utf-8"))
        matching = [case for case in cases if case.id == trace.case_id]
        if len(matching) != 1:
            raise ValueError("Trace case is not in dataset")
        result = evaluate_trajectory(matching[0], trace)
        print(json.dumps(result, indent=2))
        return 0 if result["gate_passed"] else 1
    except (ValueError, OSError, KeyError, TypeError):
        print("Invalid dataset or saved trajectory; evaluation cannot pass.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
