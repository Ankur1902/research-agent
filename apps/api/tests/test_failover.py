import pytest
from app.agents.workflow import Workflow
from app.core.config import FallbackTarget, settings
from app.core.db import Session
from app.models.entities import Organization, Research, SpendReservation, Usage
from app.schemas.contracts import Plan
from app.services import providers
from app.services.providers import (
    CircuitBreaker,
    Completion,
    FailoverProvider,
    OutcomeUncertain,
    ProviderUnavailable,
    RequestRejected,
    StructuredResponseError,
)
from sqlalchemy import select

PLAN = Plan.model_validate(
    {"objective": "o", "tasks": [{"id": "t1", "question": "q", "agent": "web_researcher"}], "output_sections": ["s"]}
)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_breaker_opens_probes_once_and_recovers():
    clock = Clock()
    breaker = CircuitBreaker(threshold=2, cooldown=30, clock=clock)
    breaker.failure()
    assert breaker.allow()  # one failure is below the threshold
    breaker.failure()
    assert breaker.state == "open" and not breaker.allow()
    clock.now = 29
    assert not breaker.allow()
    clock.now = 31
    assert breaker.allow() and breaker.state == "half_open"
    assert not breaker.allow()  # a single probe at a time
    breaker.failure()
    assert breaker.state == "open"  # failed probe re-opens immediately
    clock.now = 62
    assert breaker.allow()
    breaker.success()
    assert breaker.state == "closed" and breaker.allow() and breaker.allow()


def test_success_resets_consecutive_failures():
    breaker = CircuitBreaker(threshold=2, clock=Clock())
    breaker.failure()
    breaker.success()
    breaker.failure()
    assert breaker.state == "closed"


class Scripted(providers.LLMProvider):
    """Per-(provider, model) outcomes; records which targets were actually called."""

    script: dict[str, list] = {}
    calls: list[str] = []

    def __init__(self, name):
        self.name = name

    async def complete(self, system, data, schema):
        key = f"{self.name}:{self.model}"
        Scripted.calls.append(key)
        outcome = Scripted.script[key].pop(0) if len(Scripted.script[key]) > 1 else Scripted.script[key][0]
        if isinstance(outcome, Exception):
            raise outcome
        return Completion(PLAN, 100, 50, 5, f"req-{key}")


@pytest.fixture
def chain(monkeypatch):
    Scripted.script, Scripted.calls = {}, []
    providers._BREAKERS.clear()

    def build(name):
        def factory(model):
            instance = Scripted(name)
            instance.model = model
            return instance

        return factory

    monkeypatch.setattr(providers, "PROVIDER_TYPES", {n: build(n) for n in ("openai", "anthropic", "gemini")})
    return FailoverProvider([("openai", "p"), ("anthropic", "s")])


async def test_fails_over_when_request_was_provably_unprocessed(chain):
    Scripted.script = {"openai:p": [ProviderUnavailable("down")], "anthropic:s": [None]}
    result = await chain.complete("sys", {}, Plan)
    assert (result.provider, result.model) == ("anthropic", "s")
    assert result.failover == ["openai:p:unavailable"]


async def test_rejected_request_falls_through_without_tripping_breaker(chain):
    Scripted.script = {"openai:p": [RequestRejected("401")], "anthropic:s": [None]}
    result = await chain.complete("sys", {}, Plan)
    assert result.provider == "anthropic" and result.failover == ["openai:p:rejected"]
    assert providers.breaker_for("openai", "p").failures == 0


async def test_uncertain_outcome_is_never_replayed_on_another_provider(chain):
    Scripted.script = {"openai:p": [OutcomeUncertain("timeout")], "anthropic:s": [None]}
    with pytest.raises(OutcomeUncertain):
        await chain.complete("sys", {}, Plan)
    assert Scripted.calls == ["openai:p"]  # double-billing guard
    assert providers.breaker_for("openai", "p").failures == 1


async def test_billed_invalid_response_is_returned_not_retried_elsewhere(chain):
    receipt = Completion(PLAN, 10, 5, 1, "bad")
    Scripted.script = {"openai:p": [StructuredResponseError(receipt)], "anthropic:s": [None]}
    with pytest.raises(StructuredResponseError) as raised:
        await chain.complete("sys", {}, Plan)
    assert Scripted.calls == ["openai:p"]
    assert (raised.value.receipt.provider, raised.value.receipt.model) == ("openai", "p")  # usage attributed correctly


async def test_open_circuit_is_skipped_on_later_calls(chain):
    Scripted.script = {"openai:p": [ProviderUnavailable("down")], "anthropic:s": [None]}
    for _ in range(3):  # default threshold is 3
        await chain.complete("sys", {}, Plan)
    assert providers.breaker_for("openai", "p").state == "open"
    Scripted.calls.clear()
    result = await chain.complete("sys", {}, Plan)
    assert Scripted.calls == ["anthropic:s"] and result.failover == ["openai:p:circuit_open"]


async def test_all_unavailable_raises_a_releasable_error(chain):
    Scripted.script = {"openai:p": [ProviderUnavailable("a")], "anthropic:s": [ProviderUnavailable("b")]}
    with pytest.raises(ProviderUnavailable):
        await chain.complete("sys", {}, Plan)
    for _ in range(3):
        with pytest.raises(ProviderUnavailable):
            await chain.complete("sys", {}, Plan)
    Scripted.calls.clear()
    with pytest.raises(ProviderUnavailable, match="circuits are open"):
        await chain.complete("sys", {}, Plan)
    assert Scripted.calls == []


def test_llm_factory_only_wraps_when_fallbacks_are_configured(monkeypatch):
    config = settings()
    monkeypatch.setattr(config, "llm_fallbacks", [])
    assert not isinstance(providers.llm(), FailoverProvider)
    monkeypatch.setattr(config, "llm_provider", "openai")
    monkeypatch.setattr(config, "llm_model", "p")
    monkeypatch.setattr(
        config,
        "llm_fallbacks",
        [FallbackTarget(provider="gemini", model="g", input_price_per_million=1, output_price_per_million=2)],
    )
    assert providers.llm().targets == [("openai", "p"), ("gemini", "g")]


def test_fallback_prices_are_required_and_ceiling_covers_the_chain(monkeypatch):
    with pytest.raises(ValueError):
        FallbackTarget.model_validate({"provider": "gemini", "model": "g"})
    config = settings()
    monkeypatch.setattr(config, "llm_provider", "openai")
    monkeypatch.setattr(config, "llm_model", "p")
    monkeypatch.setattr(
        config,
        "llm_fallbacks",
        [FallbackTarget(provider="anthropic", model="s", input_price_per_million=3, output_price_per_million=15)],
    )
    assert config.price_for("anthropic", "s") == (3, 15)
    assert config.price_for("openai", "p") == (config.input_price_per_million, config.output_price_per_million)
    assert config.price_ceiling() == (max(3, config.input_price_per_million), max(15, config.output_price_per_million))


class ServedByFallback(providers.LLMProvider):
    def __init__(self):
        pass

    async def complete(self, system, data, schema):
        return Completion(
            PLAN, 1_000_000, 1_000_000, 7, "req-1", provider="anthropic", model="s", failover=["openai:p:unavailable"]
        )


class Unreachable(providers.LLMProvider):
    def __init__(self):
        pass

    async def complete(self, system, data, schema):
        raise ProviderUnavailable("every provider is down")


async def make_job(session):
    org = Organization(name="Failover org")
    session.add(org)
    await session.flush()
    job = Research(organization_id=org.id, question="Failover cost attribution test", mode="LIVE", budget=20)
    session.add(job)
    await session.commit()
    return job


async def test_usage_and_cost_follow_the_model_that_served_the_call(monkeypatch):
    from app.agents import workflow

    config = settings()
    monkeypatch.setattr(config, "llm_provider", "openai")
    monkeypatch.setattr(config, "llm_model", "p")
    monkeypatch.setattr(config, "organization_budget", 1000)
    monkeypatch.setattr(
        config,
        "llm_fallbacks",
        [FallbackTarget(provider="anthropic", model="s", input_price_per_million=3, output_price_per_million=15)],
    )
    monkeypatch.setattr(workflow, "llm", lambda: ServedByFallback())
    async with Session() as session:
        job = await make_job(session)
        await workflow.Workflow(session, job).generate("planner", {"question": "q"}, Plan)
        usage = (await session.scalars(select(Usage))).one()
        assert (usage.provider, usage.model) == ("anthropic", "s")
        assert usage.cost == pytest.approx(18.0)  # 1M * $3 + 1M * $15, not the primary's prices


async def test_unprocessed_total_outage_releases_the_budget_hold(monkeypatch):
    from app.agents import workflow

    monkeypatch.setattr(workflow, "llm", lambda: Unreachable())
    async with Session() as session:
        job = await make_job(session)
        with pytest.raises(ProviderUnavailable):
            await Workflow(session, job).generate("planner", {"question": "q"}, Plan)
        receipts = (await session.scalars(select(SpendReservation))).all()
        assert [r.status for r in receipts] == ["SETTLED"] and receipts[0].actual_cost == 0
