from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def settings() -> Settings:
    return Settings()
