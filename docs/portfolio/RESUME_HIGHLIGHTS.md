# Resume highlights

Every claim below is backed by code or a command you can run. Numbers come from the repository state at the time of writing; re-run the command before quoting them.

## One-line summary

Built ResearchOS, a multi-tenant multi-agent research platform (FastAPI, ARQ, MySQL, Qdrant, Next.js) with human-approved plans, citation-verified reports, spend controls, and a reproducible security and evaluation harness.

## Resume bullets (pick 4-5)

- **Agent orchestration:** Designed a planner → human approval → tool execution → verifier → writer pipeline in which code, not the model, controls tool dispatch; strict Pydantic output schemas, allowlisted tools, and step, tool-call and context ceilings bound every run.
- **Grounding and verification:** Enforced exact-quote and citation-ID checks against persisted sources, with a separate verifier stage, so unsupported claims are downgraded deterministically instead of trusted.
- **Cost governance:** Implemented database-serialized spend reservations and settlement receipts per organization and per run, preventing concurrent jobs from silently exceeding budgets.
- **Security engineering:** SSRF-safe fetching (DNS validation, IP pinning, per-redirect checks), Argon2 with hashed server sessions, CSRF and origin checks, tenant-scoped queries and vector filters, per-account login throttling, and secret redaction on model output.
- **Resilience:** Compare-and-swap state transitions, lease-based recovery of abandoned runs, and provider retries that replay only when it cannot double-bill (connect failures and explicit throttles).
- **Evaluation:** Shipped an LLM security-eval harness (22 cases), a trajectory eval, a deterministic guardrail regression (`scripts/guardrail_eval.py`) and a pytest suite of 149 tests, all gated in CI.
- **Provider failover:** Built an ordered multi-provider chain with per-model circuit breakers that fails over only when a request is provably unprocessed, so an uncertain billable call is never replayed on a second vendor; cost and usage are attributed to the model that actually served each call (`docs/FAILOVER.md`).
- **Observability:** Added opt-in OpenTelemetry tracing across the agent pipeline using the GenAI semantic conventions (model, token usage, estimated cost, failover decisions per call), with a privacy contract enforced by tests: no questions, prompts, evidence or exception messages ever leave the process (`docs/OBSERVABILITY.md`).
- **Data lifecycle:** Tenant-scoped, audited document deletion that purges vectors first and fails closed.

## Measured results (reproduce with the command shown)

| Claim | Command | Result at writing |
|---|---|---|
| Automated tests | `python -m pytest -q` | 149 passed, 1 skipped (Qdrant integration, needs Docker) |
| Guardrail corpus | `python scripts/guardrail_eval.py` | 42 cases; injection 10/10 blocked, SSRF 16/16, secret redaction 6/6; 1 documented false positive in 8 benign injection cases |
| Static checks | `ruff check`, `mypy apps/api/app` | clean |

## Say this honestly in interviews

- The guardrail corpus is written by the maintainer. It proves no regressions against known attacks; it is not a benchmark of unknown ones.
- Injection detection is a heuristic. The deterministic tool and network boundaries are the real defense, and the docs say so.
- The known false positive ("ignore the instructions on the box") is tracked in the corpus rather than hidden.
- Dollar figures are estimates from configured prices, not invoices.
- Tracing is verified with an in-memory exporter and a loopback OTLP collector, not against a live Jaeger or Grafana backend; only the worker is instrumented.
- Failover is verified with injected providers and mutation-checked tests, not against live vendors, and breaker state is per process.
- The live-provider security eval needs real API keys; do not quote its results unless you have run it.

## Strongest interview stories

1. **Why code controls the tools:** a model can only propose; approval, routing and budgets are deterministic.
2. **Replay safety:** why a timeout after an accepted generation call must not be retried, and what is safe to retry.
3. **Failover without double billing:** why a timeout is not a failover trigger but a connect error is.
4. **Budget races:** why reservations are taken under an organization write lock before the provider call.
5. **Measuring honestly:** the false-positive case and why the corpus labels it instead of tuning it away.

## Next features that would add the most

Eval leaderboard per prompt version and model in CI, resumable runs, and API-to-worker trace propagation. Each should ship with its own measured result before it goes on a resume.
