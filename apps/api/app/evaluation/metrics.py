from urllib.parse import urlsplit, urlunsplit


def ratio(numerator: int, denominator: int):
    return numerator / denominator if denominator else None


def evaluate_report(report: dict, expected_topics: list[str], expected_sources: list[str]):
    findings = report.get("findings", [])
    sources = report.get("sources", [])
    known = {source["citation"] for source in sources}
    cited = [citation for finding in findings for citation in finding["citations"]]
    text = " ".join(finding["text"] for finding in findings).lower()
    actual_sources = {source_identity(source["url"]) for source in sources}
    return {
        "topic_coverage": ratio(sum(topic.lower() in text for topic in expected_topics), len(expected_topics)),
        "expected_source_recall": ratio(
            sum(source_identity(url) in actual_sources for url in expected_sources), len(expected_sources)
        ),
        "citation_mapping_precision": ratio(sum(citation in known for citation in cited), len(cited)),
        "claim_support_rate": ratio(sum(finding["status"] == "VERIFIED" for finding in findings), len(findings)),
        "citation_coverage": ratio(
            sum(bool(finding["citations"]) for finding in findings if finding["kind"] == "FACT"),
            sum(finding["kind"] == "FACT" for finding in findings),
        ),
    }


def source_identity(value: str) -> str:
    """Normalize URL identity without matching another URL embedded in a query."""
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"}:
            return value
        host = (parts.hostname or "").lower()
        if ":" in host:
            host = f"[{host}]"
        port = parts.port
        if port and (parts.scheme.lower(), port) not in {("http", 80), ("https", 443)}:
            host += f":{port}"
        return urlunsplit((parts.scheme.lower(), host, parts.path or "/", parts.query, ""))
    except ValueError:
        return value
