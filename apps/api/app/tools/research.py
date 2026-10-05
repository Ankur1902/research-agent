from app.security.guards import fetch_public
from app.services.providers import search_provider
from app.tools.registry import Tool, ToolRegistry
from pydantic import BaseModel, Field


class QueryInput(BaseModel):
    query: str = Field(min_length=1, max_length=4000)


class FetchInput(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


def research_tools(document_handler):
    tools = ToolRegistry()
    tools.register(
        Tool(
            "web_search",
            "Search approved public web research sources",
            QueryInput,
            lambda data: search_provider().search(data.query),
            "READ_ONLY",
        )
    )
    tools.register(
        Tool(
            "fetch_webpage",
            "Fetch a public text page with pinned DNS and redirect validation",
            FetchInput,
            lambda data: fetch_public(data.url),
            "READ_ONLY",
        )
    )
    tools.register(
        Tool(
            "document_search",
            "Retrieve organization-filtered indexed document evidence",
            QueryInput,
            lambda data: document_handler(data.query),
            "SENSITIVE",
        )
    )
    return tools
