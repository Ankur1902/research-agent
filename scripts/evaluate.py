"""Reproducible, explicitly synthetic metric regression."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from app.evaluation.metrics import evaluate_report  # noqa: E402

fixture = {
    "findings": [{"text": "The fixture requires approval.", "kind": "FACT", "status": "VERIFIED", "citations": ["S1"]}],
    "sources": [{"citation": "S1", "url": "demo:fixture"}],
}
print(
    json.dumps(
        {
            "mode": "DEMO",
            "method": "synthetic fixture regression",
            "metrics": evaluate_report(fixture, ["approval"], ["demo:fixture"]),
        },
        indent=2,
    )
)
