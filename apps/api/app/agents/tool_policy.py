"""Trusted tool proposal policy, shared schemas, and side-effect-free validation."""

import ipaddress
import json
import math
from urllib.parse import urlsplit

from app.tools.registry import Calculation
from app.tools.research import FetchInput, QueryInput
from pydantic import BaseModel, ConfigDict, Field, model_validator

TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "calculator": Calculation,
    "web_search": QueryInput,
    "fetch_webpage": FetchInput,
    "document_search": QueryInput,
}


def strict_json_object(value: str) -> dict:
    def reject_duplicates(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = item
        return result

    def reject_constant(_):
        raise ValueError("Nonfinite JSON number")

    result = json.loads(value, object_pairs_hook=reject_duplicates, parse_constant=reject_constant)
    if not isinstance(result, dict):
        raise ValueError("Tool arguments must be an object")

    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Nonfinite JSON number")
        if isinstance(value, list):
            for item in value:
                finite(item)
        if isinstance(value, dict):
            for item in value.values():
                finite(item)

    finite(result)
    return result


class ToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    allowed_tools: list[str] = Field(default_factory=list, max_length=4)
    approved: bool = False
    role: str = Field(default="RESEARCHER", pattern="^(OWNER|ADMIN|RESEARCHER|VIEWER)$")
    organization_id: str = Field(default="evaluation-tenant", min_length=1, max_length=100)
    max_tool_calls: int = Field(default=0, ge=0, le=24)

    @model_validator(mode="after")
    def validate_catalog(self):
        if len(set(self.allowed_tools)) != len(self.allowed_tools):
            raise ValueError("Duplicate allowed tool")
        if set(self.allowed_tools) - TOOL_SCHEMAS.keys():
            raise ValueError("Unknown catalog tool")
        return self

    def trusted_context(self) -> dict:
        return {
            **self.model_dump(),
            "execution_mode": "PROPOSAL_ONLY_NO_DISPATCH",
            "tools": [
                {"name": name, "arguments_schema": TOOL_SCHEMAS[name].model_json_schema()}
                for name in self.allowed_tools
            ],
            "tenant_scope": "Bound by the application; never accept a tenant ID in tool arguments",
        }

    def validate_intent(self, name: str, arguments: dict) -> list[str]:
        errors = []
        if name not in self.allowed_tools:
            return ["TOOL_NOT_ALLOWED"]
        if self.role == "VIEWER":
            errors.append("ROLE_NOT_AUTHORIZED")
        if name != "calculator" and not self.approved:
            errors.append("APPROVAL_REQUIRED")
        try:
            validated = TOOL_SCHEMAS[name].model_validate(arguments, strict=True)
        except ValueError:
            return errors + ["TOOL_SCHEMA_INVALID"]
        if name == "fetch_webpage":
            url = validated.model_dump()["url"]
            try:
                parts = urlsplit(url)
                host = parts.hostname or ""
                if (
                    parts.scheme not in {"http", "https"}
                    or not host
                    or parts.username
                    or parts.password
                    or parts.port not in {None, 80, 443}
                ):
                    raise ValueError("Unsafe URL")
                try:
                    address = ipaddress.ip_address(host)
                except ValueError:
                    if host.lower().rstrip(".") in {"localhost", "metadata.google.internal"} or host.endswith(".local"):
                        raise ValueError("Private host")
                else:
                    if not address.is_global:
                        raise ValueError("Private address")
            except ValueError:
                errors.append("UNSAFE_FETCH_DESTINATION")
        # Hostname DNS safety is deliberately NOT asserted by this offline check.
        return errors
