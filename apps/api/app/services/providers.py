import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from app.core.config import settings
from pydantic import BaseModel

MAX_PROVIDER_HTTP_ATTEMPTS = 3


@dataclass
class Completion:
    value: BaseModel
    input_tokens: int
    output_tokens: int
    latency_ms: int
    request_id: str
    http_attempts: int | None = None


class StructuredResponseError(ValueError):
    """A billable response failed validation; preserve its usage receipt."""

    def __init__(self, receipt: Completion):
        super().__init__("Provider returned an incomplete or invalid structured response")
        self.receipt = receipt


class RequestRejected(RuntimeError):
    """The provider explicitly declined the request before generation."""


class EmptyResponse(BaseModel):
    pass


def validated_completion(schema, content, input_tokens, output_tokens, start, request_id, attempts, *, complete=True):
    receipt = Completion(
        EmptyResponse(), input_tokens, output_tokens, int((time.monotonic() - start) * 1000), request_id, attempts
    )
    try:
        if not complete:
            raise ValueError("Incomplete response")
        receipt.value = schema.model_validate_json(content)
    except ValueError:
        raise StructuredResponseError(receipt) from None
    return receipt


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, data: dict, schema: type[BaseModel]) -> Completion: ...


async def request_json(url, headers, body, *, retry_ambiguous=True):
    async with httpx.AsyncClient(timeout=90) as client:
        for attempt in range(MAX_PROVIDER_HTTP_ATTEMPTS):
            try:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict):
                    raise RuntimeError("Provider returned an invalid JSON envelope")
                result["_researchos_http_attempts"] = attempt + 1
                return result
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in {429, 500, 502, 503, 504}:
                    raise RequestRejected(f"Provider rejected request ({exc.response.status_code})") from None
                # Generation timeouts and server errors can follow accepted,
                # billable work. Retry only an explicit throttle response.
                if not retry_ambiguous and (
                    not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code != 429
                ):
                    raise RuntimeError("Provider outcome uncertain; automatic replay disabled") from None
                if attempt == MAX_PROVIDER_HTTP_ATTEMPTS - 1:
                    raise RuntimeError("Provider unavailable after bounded retries") from None
                await asyncio.sleep(2**attempt)
    raise RuntimeError("Provider request failed")


class OpenAIProvider(LLMProvider):
    async def complete(self, system, data, schema):
        config = settings()
        if not config.openai_api_key:
            raise RequestRejected("OPENAI_API_KEY is required for live OpenAI research")
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
            retry_ambiguous=False,
        )
        return validated_completion(
            schema,
            result["choices"][0]["message"]["content"],
            result["usage"]["prompt_tokens"],
            result["usage"]["completion_tokens"],
            start,
            result["id"],
            result.get("_researchos_http_attempts"),
        )


class AnthropicProvider(LLMProvider):
    async def complete(self, system, data, schema):
        config = settings()
        if not config.anthropic_api_key:
            raise RequestRejected("ANTHROPIC_API_KEY is required")
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
            retry_ambiguous=False,
        )
        content = "".join(block.get("text", "") for block in result["content"])
        return validated_completion(
            schema,
            content,
            result["usage"]["input_tokens"],
            result["usage"]["output_tokens"],
            start,
            result["id"],
            result.get("_researchos_http_attempts"),
        )


def gemini_schema(schema: type[BaseModel]) -> dict:
    """Inline local references and omit transport-only size constraints.

    Gemini rejects some complex bounded-array schemas. The original Pydantic
    model remains authoritative for all bounds and extra-field validation.
    """
    source = schema.model_json_schema()
    definitions = source.get("$defs", {})

    def convert(node, refs=()):
        if isinstance(node, list):
            return [convert(item, refs) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            name = node["$ref"].removeprefix("#/$defs/")
            if name not in definitions or name in refs:
                raise ValueError("Unsupported recursive or external Gemini schema reference")
            return convert(definitions[name], (*refs, name))
        return {
            key: convert(value, refs)
            for key, value in node.items()
            if key not in {"$defs", "maxItems", "minItems", "minLength", "maxLength"}
        }

    return convert(source)


class GeminiProvider(LLMProvider):
    async def complete(self, system, data, schema):
        config = settings()
        if not config.google_api_key:
            raise RequestRejected("GOOGLE_API_KEY is required")
        start = time.monotonic()
        result = await request_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{config.llm_model}:generateContent",
            {"x-goog-api-key": config.google_api_key},
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": json.dumps(data)}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": gemini_schema(schema),
                    "maxOutputTokens": 4000,
                },
            },
            retry_ambiguous=False,
        )
        candidates = result.get("candidates", [])
        candidate = candidates[0] if candidates else {}
        content = "".join(
            part.get("text", "")
            for part in candidate.get("content", {}).get("parts", [])
            if not part.get("thought", False)
        )
        usage = result.get("usageMetadata", {})
        return validated_completion(
            schema,
            content,
            usage.get("promptTokenCount", 0),
            usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0),
            start,
            result.get("responseId", ""),
            result.get("_researchos_http_attempts"),
            complete=bool(content) and candidate.get("finishReason") in {None, "STOP"},
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
            "https://api.tavily.com/search",
            {},
            {"api_key": config.search_api_key, "query": query, "max_results": 4},
            retry_ambiguous=False,
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
