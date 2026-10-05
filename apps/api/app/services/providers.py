import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from app.core.config import settings
from pydantic import BaseModel


@dataclass
class Completion:
    value: BaseModel
    input_tokens: int
    output_tokens: int
    latency_ms: int
    request_id: str


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, data: dict, schema: type[BaseModel]) -> Completion: ...


async def request_json(url, headers, body):
    async with httpx.AsyncClient(timeout=90) as client:
        for attempt in range(3):
            try:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in {429, 500, 502, 503, 504}:
                    raise RuntimeError(f"Provider rejected request ({exc.response.status_code})") from None
                if attempt == 2:
                    raise RuntimeError("Provider unavailable after bounded retries") from None
                await asyncio.sleep(2**attempt)
    raise RuntimeError("Provider request failed")


class OpenAIProvider(LLMProvider):
    async def complete(self, system, data, schema):
        config = settings()
        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for live OpenAI research")
        start = time.monotonic()
        result = await request_json(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {config.openai_api_key}"},
            {
                "model": config.llm_model,
                "max_completion_tokens": 4000,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(data)}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": schema.__name__, "strict": True, "schema": schema.model_json_schema()},
                },
            },
        )
        return Completion(
            schema.model_validate_json(result["choices"][0]["message"]["content"]),
            result["usage"]["prompt_tokens"],
            result["usage"]["completion_tokens"],
            int((time.monotonic() - start) * 1000),
            result["id"],
        )


class AnthropicProvider(LLMProvider):
    async def complete(self, system, data, schema):
        config = settings()
        if not config.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        start = time.monotonic()
        result = await request_json(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": config.anthropic_api_key, "anthropic-version": "2023-06-01"},
            {
                "model": config.llm_model,
                "max_tokens": 4000,
                "system": system,
                "messages": [{"role": "user", "content": json.dumps(data)}],
                "output_config": {"format": {"type": "json_schema", "schema": schema.model_json_schema()}},
            },
        )
        content = "".join(block.get("text", "") for block in result["content"])
        return Completion(
            schema.model_validate_json(content),
            result["usage"]["input_tokens"],
            result["usage"]["output_tokens"],
            int((time.monotonic() - start) * 1000),
            result["id"],
        )


class GeminiProvider(LLMProvider):
    async def complete(self, system, data, schema):
        config = settings()
        if not config.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required")
        start = time.monotonic()
        result = await request_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{config.llm_model}:generateContent",
            {"x-goog-api-key": config.google_api_key},
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": json.dumps(data)}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema.model_json_schema(),
                    "maxOutputTokens": 4000,
                },
            },
        )
        usage = result["usageMetadata"]
        return Completion(
            schema.model_validate_json(result["candidates"][0]["content"]["parts"][0]["text"]),
            usage["promptTokenCount"],
            usage.get("candidatesTokenCount", 0),
            int((time.monotonic() - start) * 1000),
            result.get("responseId", ""),
        )


def llm() -> LLMProvider:
    providers: dict[str, type[LLMProvider]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "gemini": GeminiProvider,
    }
    if settings().llm_provider not in providers:
        raise ValueError("Unsupported LLM_PROVIDER")
    return providers[settings().llm_provider]()


class SearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str) -> list[dict]: ...


class TavilySearch(SearchProvider):
    async def search(self, query):
        config = settings()
        if not config.search_api_key:
            raise ValueError("SEARCH_API_KEY is required for web research")
        result = await request_json(
            "https://api.tavily.com/search", {}, {"api_key": config.search_api_key, "query": query, "max_results": 4}
        )
        return [{"title": item["title"], "url": item["url"]} for item in result["results"]]


class BraveSearch(SearchProvider):
    async def search(self, query):
        if not settings().search_api_key:
            raise ValueError("SEARCH_API_KEY is required")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": 4},
                headers={"X-Subscription-Token": settings().search_api_key},
            )
            response.raise_for_status()
            return [
                {"title": item["title"], "url": item["url"]}
                for item in response.json().get("web", {}).get("results", [])
            ]


def search_provider() -> SearchProvider:
    providers = {"tavily": TavilySearch, "brave": BraveSearch}
    if settings().search_provider not in providers:
        raise ValueError("Unsupported SEARCH_PROVIDER")
    return providers[settings().search_provider]()


async def embed(texts: list[str]) -> list[list[float]]:
    if not settings().openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for embeddings, independently of generation provider")
    result = await request_json(
        "https://api.openai.com/v1/embeddings",
        {"Authorization": f"Bearer {settings().openai_api_key}"},
        {"model": settings().embedding_model, "input": texts},
    )
    return [entry["embedding"] for entry in sorted(result["data"], key=lambda entry: entry["index"])]
