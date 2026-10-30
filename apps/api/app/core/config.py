from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRETS = ("replace-with", "change-me", "changeme")


class FallbackTarget(BaseModel):
    """A secondary model used when the primary is unreachable. Prices are mandatory so cost stays honest."""

    model_config = ConfigDict(extra="forbid")
    provider: Literal["openai", "anthropic", "gemini"]
    model: str = Field(min_length=1, max_length=100)
    input_price_per_million: float = Field(ge=0)
    output_price_per_million: float = Field(ge=0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "mysql+aiomysql://researchos:researchos@mysql:3306/researchos"
    redis_url: str = "redis://redis:6379/0"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "document_chunks"
    auth_secret: str = ""
    environment: str = "development"
    public_origin: str = "http://localhost:3000"
    llm_provider: str = "openai"
    llm_model: str = "gpt-4.1-mini"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    search_provider: str = "tavily"
    search_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    retrieval_backend: Literal["hybrid", "lexical"] = "hybrid"
    input_price_per_million: float = 0.4
    output_price_per_million: float = 1.6
    search_price_per_call: float = 0.008
    organization_budget: float = 50
    max_upload_bytes: int = 10 * 1024 * 1024
    max_context_chars: int = 30000
    max_steps: int = 12
    max_tool_calls: int = 24
    max_requests_per_minute: int = 120
    # JSON list, e.g. [{"provider":"gemini","model":"...","input_price_per_million":0.3,"output_price_per_million":2.5}]
    llm_fallbacks: list[FallbackTarget] = Field(default_factory=list, max_length=3)
    # Proxies between the internet and the API that append the peer address to X-Forwarded-For. Keep 0 unless
    # an edge proxy you control sets it; otherwise clients can spoof their rate-limit identity.
    trusted_proxy_count: int = Field(default=0, ge=0, le=5)
    # Opt-in tracing. "otlp" also honors the standard OTEL_EXPORTER_OTLP_* variables (endpoint, headers).
    otel_traces_exporter: Literal["none", "console", "otlp"] = "none"
    otel_service_name: str = "researchos-worker"
    otel_sample_ratio: float = Field(default=1.0, ge=0, le=1)
    breaker_failure_threshold: int = Field(default=3, ge=1)
    breaker_cooldown_seconds: float = Field(default=60, gt=0)

    def price_for(self, provider: str | None, model: str | None) -> tuple[float, float]:
        """Per-million (input, output) price of the model that actually served a call."""
        for target in self.llm_fallbacks:
            if (target.provider, target.model) == (provider, model) and (provider, model) != (
                self.llm_provider,
                self.llm_model,
            ):
                return target.input_price_per_million, target.output_price_per_million
        return self.input_price_per_million, self.output_price_per_million

    def price_ceiling(self) -> tuple[float, float]:
        """Worst-case prices across the chain, so reservations cover whichever model ends up serving."""
        inputs = [self.input_price_per_million, *(t.input_price_per_million for t in self.llm_fallbacks)]
        outputs = [self.output_price_per_million, *(t.output_price_per_million for t in self.llm_fallbacks)]
        return max(inputs), max(outputs)


def production_problems(config: Settings) -> list[str]:
    """Configuration that must never reach a production deployment."""
    if config.environment != "production":
        return []
    problems = []
    if len(config.auth_secret) < 32 or any(marker in config.auth_secret.lower() for marker in PLACEHOLDER_SECRETS):
        problems.append("AUTH_SECRET must be a random value of at least 32 characters")
    if not config.public_origin.startswith("https://"):
        problems.append("PUBLIC_ORIGIN must use https")
    if any(marker in config.database_url.lower() for marker in ("researchos:researchos@", "change-me")):
        problems.append("DATABASE_URL uses a default credential")
    return problems


@lru_cache
def settings() -> Settings:
    return Settings()
