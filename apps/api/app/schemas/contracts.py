from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(Strict):
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=10, max_length=128)


class Register(Credentials):
    name: str = Field(min_length=1, max_length=120)
    organization: str = Field(min_length=1, max_length=120)


class ProjectInput(Strict):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)


class ResearchInput(Strict):
    question: str = Field(min_length=10, max_length=4000)
    project_id: str | None = None
    depth: Literal["quick", "standard", "deep"] = "standard"
    source_mode: Literal["web", "documents", "both"] = "both"
    mode: Literal["LIVE", "DEMO"] = "LIVE"
    budget: float = Field(default=1, gt=0, le=20)


class Task(Strict):
    id: str
    question: str
    agent: Literal["web_researcher", "knowledge_agent"]


class Plan(Strict):
    objective: str
    tasks: list[Task] = Field(min_length=1, max_length=8)
    output_sections: list[str] = Field(min_length=1, max_length=12)


class Finding(Strict):
    text: str
    kind: Literal["FACT", "ANALYSIS", "INFERENCE", "RECOMMENDATION"]
    citations: list[str]
    quote: str
    status: Literal["VERIFIED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONFLICTING"]


class Computation(Strict):
    operation: Literal["sum", "mean", "min", "max", "growth_percent"]
    values: list[float] = Field(min_length=1, max_length=100)
    citation: str
    quote: str


class Analysis(Strict):
    findings: list[Finding] = Field(max_length=30)
    limitations: list[str]
    computations: list[Computation] = Field(max_length=8)


class Section(Strict):
    title: str
    finding_indices: list[int]


class Report(Strict):
    title: str
    summary: str
    sections: list[Section]
    limitations: list[str]


class Assessment(Strict):
    statuses: list[Literal["VERIFIED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONFLICTING"]]


class Preferences(Strict):
    default_depth: Literal["quick", "standard", "deep"] = "standard"
    monthly_budget: float = Field(default=50, gt=0, le=10000)
