"""Explicit expected-versus-observed evaluation contracts."""

from collections import Counter

from app.agents.tool_policy import strict_json_object
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CountRange(StrictContract):
    minimum: int = Field(ge=0, le=10000)
    maximum: int = Field(ge=0, le=10000)

    @model_validator(mode="after")
    def ordered(self):
        if self.minimum > self.maximum:
            raise ValueError("Minimum exceeds maximum")
        return self


class ArgumentExpectation(StrictContract):
    tool: str = Field(min_length=1, max_length=80)
    occurrence: int = Field(ge=0, le=23)
    arguments_json: str = Field(min_length=2, max_length=8000)

    @model_validator(mode="after")
    def valid_arguments(self):
        strict_json_object(self.arguments_json)
        return self


class CallExpectations(StrictContract):
    tool_calls: CountRange
    per_tool: dict[str, CountRange]
    sequence: list[str] | None
    arguments: list[ArgumentExpectation]
    model_calls: dict[str, CountRange]
    max_latency_ms: int | None = Field(default=None, gt=0)
    max_total_tokens: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def coherent(self):
        if sum(item.minimum for item in self.per_tool.values()) > self.tool_calls.maximum:
            raise ValueError("Per-tool minimum exceeds total maximum")
        if sum(item.maximum for item in self.per_tool.values()) < self.tool_calls.minimum:
            raise ValueError("Per-tool maximum cannot meet total minimum")
        if self.sequence is not None:
            counts = Counter(self.sequence)
            if not self.tool_calls.minimum <= len(self.sequence) <= self.tool_calls.maximum:
                raise ValueError("Sequence count inconsistent with total")
            if set(counts) - self.per_tool.keys():
                raise ValueError("Sequence contains an unspecified tool")
            if any(not bounds.minimum <= counts[name] <= bounds.maximum for name, bounds in self.per_tool.items()):
                raise ValueError("Sequence inconsistent with per-tool count")
        keys = [(item.tool, item.occurrence) for item in self.arguments]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate argument expectation")
        for item in self.arguments:
            if item.tool not in self.per_tool or item.occurrence >= self.per_tool[item.tool].maximum:
                raise ValueError("Argument expectation cannot match an allowed occurrence")
        return self


class ContractCheck(StrictContract):
    name: str
    passed: bool
    expected: str
    observed: str


def evaluate_calls(
    expected: CallExpectations,
    calls: list[tuple[str, dict | None]],
    model_calls: dict[str, int],
    *,
    latency_ms: int | None = None,
    total_tokens: int | None = None,
) -> list[ContractCheck]:
    checks = []

    def count_check(name: str, bounds: CountRange, observed: int):
        checks.append(
            ContractCheck(
                name=name,
                passed=bounds.minimum <= observed <= bounds.maximum,
                expected=f"{bounds.minimum}..{bounds.maximum}",
                observed=str(observed),
            )
        )

    count_check("tool_calls.total", expected.tool_calls, len(calls))
    counts = Counter(name for name, _ in calls)
    for name in sorted(set(counts) | set(expected.per_tool)):
        count_check(f"tool_calls.{name}", expected.per_tool.get(name, CountRange(minimum=0, maximum=0)), counts[name])
    for name in sorted(set(model_calls) | set(expected.model_calls)):
        count_check(
            f"model_calls.{name}",
            expected.model_calls.get(name, CountRange(minimum=0, maximum=0)),
            model_calls.get(name, 0),
        )
    if expected.sequence is not None:
        observed = [name for name, _ in calls]
        checks.append(
            ContractCheck(
                name="tool_calls.sequence",
                passed=observed == expected.sequence,
                expected=",".join(expected.sequence),
                observed=",".join(observed),
            )
        )
    for item in expected.arguments:
        matches = [arguments for name, arguments in calls if name == item.tool]
        matched = len(matches) > item.occurrence and matches[item.occurrence] == strict_json_object(item.arguments_json)
        # Persist match outcome, not raw potentially sensitive tool arguments.
        checks.append(
            ContractCheck(
                name=f"tool_arguments.{item.tool}.{item.occurrence}",
                passed=matched,
                expected="exact fixture arguments",
                observed="match" if matched else "mismatch or missing",
            )
        )
    for name, limit, value in (
        ("latency_ms", expected.max_latency_ms, latency_ms),
        ("total_tokens", expected.max_total_tokens, total_tokens),
    ):
        if limit is not None:
            checks.append(
                ContractCheck(
                    name=name,
                    passed=value is not None and value <= limit,
                    expected=f"<= {limit}",
                    observed=str(value) if value is not None else "not measured",
                )
            )
    return checks
