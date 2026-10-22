"""Adapter-level fixtures: no network or real credentials."""

import json

import pytest
from app.core.config import settings
from app.schemas.contracts import Plan
from app.services import providers


@pytest.mark.parametrize("valid", [True, False])
async def test_gemini_preserves_tokens_including_thoughts_on_schema_failure(monkeypatch, valid):
    monkeypatch.setattr(settings(), "google_api_key", "synthetic-key")
    plan = {
        "objective": "Inspect policy",
        "tasks": [{"id": "a", "question": "Notice deadline?", "agent": "knowledge_agent"}],
        "output_sections": ["Findings"],
    }

    async def response(*args, **kwargs):
        assert kwargs["retry_ambiguous"] is False
        return {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {"thought": True, "text": "not evidence"},
                            {"text": json.dumps(plan) if valid else "{}"},
                        ]
                    },
                }
            ],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20, "thoughtsTokenCount": 5},
            "responseId": "fixture",
            "_researchos_http_attempts": 1,
        }

    monkeypatch.setattr(providers, "request_json", response)
    if valid:
        receipt = await providers.GeminiProvider().complete("system", {}, Plan)
        assert receipt.value == Plan.model_validate(plan)
    else:
        with pytest.raises(providers.StructuredResponseError) as error:
            await providers.GeminiProvider().complete("system", {}, Plan)
        receipt = error.value.receipt
    assert (receipt.input_tokens, receipt.output_tokens, receipt.request_id) == (100, 25, "fixture")
