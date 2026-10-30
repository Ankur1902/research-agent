"""Deterministic adversarial regression for the non-LLM guardrails (no network, no API keys).

The corpus is authored by the maintainers, so this measures regressions against known attacks,
not resistance to unknown ones.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.security.guards import detect_injection, public_url, redact_secrets  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "packages" / "evals" / "guardrails" / "cases.v1.jsonl"


def blocked(category: str, text: str) -> bool:
    if category == "injection":
        return detect_injection(text)
    if category == "secret_leak":
        return redact_secrets(text) != text
    try:
        public_url(text)
    except ValueError:
        return True
    return False


def main() -> int:
    stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"attacks": 0, "blocked": 0, "benign": 0, "false_positives": 0}
    )
    misses, known = [], []
    for line in CASES.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        result = blocked(case["category"], case["input"])
        row = stats[case["category"]]
        if case["expect_blocked"]:
            row["attacks"] += 1
            row["blocked"] += result
        else:
            row["benign"] += 1
            row["false_positives"] += result
        if result != case["expect_blocked"]:
            (known if case.get("known_limitation") else misses).append(case["id"])
    report = {
        category: {
            **row,
            "block_rate": row["blocked"] / row["attacks"] if row["attacks"] else None,
            "false_positive_rate": row["false_positives"] / row["benign"] if row["benign"] else None,
        }
        for category, row in stats.items()
    }
    print(
        json.dumps(
            {"categories": report, "known_limitations": known, "unexpected_misclassifications": misses}, indent=2
        )
    )
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(main())
