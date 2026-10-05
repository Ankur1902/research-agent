import csv
import io
import statistics
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from pydantic import BaseModel, Field


class Calculation(BaseModel):
    operation: str = Field(pattern="^(sum|mean|min|max|growth_percent)$")
    values: list[float] = Field(min_length=1, max_length=10000)


def calculate(data: Calculation) -> dict:
    values = [Decimal(str(value)) for value in data.values]
    if data.operation == "growth_percent":
        if len(values) != 2 or not values[0]:
            raise ValueError("Growth requires two values and a nonzero base")
        result = (values[1] - values[0]) / values[0] * 100
    else:
        operations: dict[str, Callable[[], Decimal]] = {
            "sum": lambda: sum(values, Decimal(0)),
            "mean": lambda: sum(values, Decimal(0)) / len(values),
            "min": lambda: min(values),
            "max": lambda: max(values),
        }
        result = operations[data.operation]()
    return {"result": float(result), "operation": data.operation}


def inspect_csv(text: str, column: str) -> dict:
    rows = list(csv.DictReader(io.StringIO(text)))
    if len(rows) > 10000:
        raise ValueError("CSV row limit exceeded")
    values = [float(row[column]) for row in rows if row.get(column)]
    if not values:
        raise ValueError("No numeric values in requested column")
    return {
        "count": len(values),
        "sum": sum(values),
        "mean": statistics.mean(values),
        "min": min(values),
        "max": max(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0,
    }


@dataclass
class Tool:
    name: str
    description: str
    schema: type[BaseModel]
    handler: Callable
    permission: str = "LOW_RISK"


class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        if tool.name in self.tools:
            raise ValueError("Duplicate tool")
        self.tools[tool.name] = tool

    async def call(self, name: str, arguments: dict[str, Any], *, role: str, approved: bool = False):
        import inspect

        tool = self.tools.get(name)
        if not tool:
            raise ValueError("Tool is not allowlisted")
        if role == "VIEWER" or (tool.permission == "HIGH_IMPACT" and not approved):
            raise PermissionError("Tool requires authorization")
        result = tool.handler(tool.schema.model_validate(arguments))
        return await result if inspect.isawaitable(result) else result


registry = ToolRegistry()
registry.register(Tool("calculator", "Bounded decimal arithmetic; no code execution", Calculation, calculate))
