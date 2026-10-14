"""Mock HTTP transport checks; no provider endpoint is contacted."""

import httpx
import pytest
from app.services import providers


@pytest.mark.parametrize("statuses, expected", [([200], 1), ([429, 503, 200], 3)])
async def test_retry_attempt_metadata(statuses, expected, monkeypatch):
    attempts = []

    def handler(request):
        attempts.append(request.url.path)
        return httpx.Response(statuses[len(attempts) - 1], json={"value": "synthetic"})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        providers.httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs)
    )

    async def no_delay(seconds):
        pass

    monkeypatch.setattr(providers.asyncio, "sleep", no_delay)
    result = await providers.request_json("https://fixture.invalid/completions", {}, {})
    assert result["_researchos_http_attempts"] == len(attempts) == expected


async def test_permanent_error_is_not_retried_or_disclosed(monkeypatch):
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(403, text="private-provider-payload")

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        providers.httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs)
    )
    with pytest.raises(RuntimeError, match="Provider rejected request") as error:
        await providers.request_json("https://fixture.invalid/completions", {}, {})
    assert len(attempts) == 1
    assert "private-provider-payload" not in str(error.value)


async def test_transient_errors_stop_at_transport_limit(monkeypatch):
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(503, json={"error": "synthetic outage"})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        providers.httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs)
    )

    async def no_delay(seconds):
        pass

    monkeypatch.setattr(providers.asyncio, "sleep", no_delay)
    with pytest.raises(RuntimeError, match="bounded retries"):
        await providers.request_json("https://fixture.invalid/completions", {}, {})
    assert len(attempts) == providers.MAX_PROVIDER_HTTP_ATTEMPTS
