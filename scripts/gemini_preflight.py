"""Minimal live structured-output check; prints no credentials or provider payloads."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from app.core.config import settings  # noqa: E402
from app.services.providers import GeminiProvider  # noqa: E402
from pydantic import BaseModel, ConfigDict  # noqa: E402


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


async def main():
    try:
        result = await GeminiProvider().complete("Return the required JSON with ok=true.", {}, HealthResponse)
        print(
            {
                "model": settings().llm_model,
                "structured_output_valid": result.value.model_dump() == {"ok": True},
                "latency_ms": result.latency_ms,
            }
        )
    except Exception as error:
        print({"model": settings().llm_model, "structured_output_valid": False, "error_type": type(error).__name__})
        raise SystemExit(1) from None


if __name__ == "__main__":
    asyncio.run(main())
