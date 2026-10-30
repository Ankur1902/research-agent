# Tracing (OpenTelemetry)

Tracing is **off by default** and costs nothing until enabled. It is implemented in `apps/api/app/core/telemetry.py`; every call is a no-op unless an exporter is configured, and a misconfigured exporter logs a warning instead of failing a run.

## What is traced

Each research phase is one trace. Planning and execution are separate traces because approval can arrive hours apart.

```
research.run                      phase, research id, organization id, mode, depth, source mode, outcome
├─ agent.planner                  one span per model call: planner, analyst, verifier, writer
├─ research.collect_web
│  ├─ tool.web_search             result count
│  └─ tool.fetch_webpage × N      response size
├─ research.collect_documents
│  └─ tool.document_search
├─ agent.analyst
├─ tool.calculator
├─ agent.verifier
└─ agent.writer
```

Model spans use the OpenTelemetry GenAI attribute names, so GenAI-aware backends (Langfuse, Phoenix, Grafana, Jaeger) can chart them:

| Attribute | Meaning |
|---|---|
| `gen_ai.operation.name` | `chat` |
| `gen_ai.provider.name` | the provider that actually answered (after failover) |
| `gen_ai.request.model` / `gen_ai.response.model` | configured primary / model that served the call |
| `gen_ai.response.id` | provider request id |
| `gen_ai.usage.input_tokens` / `output_tokens` | provider-reported usage |
| `researchos.cost.estimated_usd`, `researchos.reserved_usd` | estimated cost and the budget hold taken before the call |
| `researchos.latency_ms`, `researchos.http_attempts` | provider latency and transport attempts |
| `researchos.prompt_sha256` | which prompt version ran, without recording it |
| `researchos.failover_skipped` | targets skipped; each skip is also a `failover.skip` span event with the reason and breaker state |

Persisted `planning_started` and `execution_authorized` events carry `trace_id`, so a run in the app can be matched to its trace in the backend.

## What is never recorded

Questions, prompts, retrieved evidence, uploaded text, source URLs, tool arguments, report content and **exception messages**. Spans hold identifiers, hashes, counts, token usage, cost and error *types* only. A failed span has status `ERROR` with the exception class name as the description. Tests assert these properties by searching everything a backend would receive for planted marker strings, including through a failing provider.

## Enable

| Setting | Values |
|---|---|
| `OTEL_TRACES_EXPORTER` | `none` (default), `console` (prints spans to the worker log), `otlp` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | collector base URL, e.g. `http://jaeger:4318`; standard `OTEL_EXPORTER_OTLP_*` variables such as headers also apply |
| `OTEL_SAMPLE_RATIO` | 0 to 1, parent-based, default 1 |
| `OTEL_SERVICE_NAME` | default `researchos-worker` |

Local viewer: set the variables above in `.env`, run `docker compose --profile observability up`, and open http://localhost:16686. Spans are flushed when the worker stops.

## Limitations

- Only the worker is instrumented. API requests are not traced and there is no context propagation from an API request into the worker, so a request and its run are linked by `research_id`, not by a shared trace.
- Traces only: no metrics or log export.
- The span structure, privacy rules and OTLP/HTTP export are covered by tests, including a loopback collector that decodes the exported protobuf. Running against a real Jaeger was **not** verified in the authoring environment, and the `jaeger` image is pinned but untested here.
