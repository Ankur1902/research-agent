# Provider failover and circuit breaker

`LLM_FALLBACKS` adds an ordered chain behind the primary `LLM_PROVIDER` / `LLM_MODEL`. With no fallbacks configured, behavior is unchanged.

## When it fails over

A generation call is billable and cannot be safely replayed once the provider may have accepted it. Failover therefore depends on what is known about the failed request:

| Failure | Fail over? | Breaker |
|---|---|---|
| Connection failed before the request was sent | yes | counts |
| Throttled (429) after bounded retries | yes | counts |
| Provider declined the request (4xx, missing key) | yes | not counted |
| Timeout, 5xx, dropped connection, non-JSON reply | **no**, the run fails with an "uncertain outcome" error | counts |
| Billable response that failed schema validation | **no**, usage is recorded against the model that answered | success |

Sending an uncertain request to a second vendor could bill both, so it is never done. The uncertain case still trips the breaker, so later calls skip the unhealthy provider instead of waiting on it.

## Circuit breaker

Per `(provider, model)`: `closed` → `open` after `BREAKER_FAILURE_THRESHOLD` consecutive counted failures → one `half_open` probe after `BREAKER_COOLDOWN_SECONDS` → `closed` on success, `open` again on failure.

## Cost and traceability

- Each fallback carries its own prices; usage rows and cost use the model that actually served the call.
- Budget reservations use the highest price in the chain, so a pricier fallback cannot overrun a hold.
- If no provider was reached (all unreachable or all circuits open), the reservation is released at zero.
- `agent_completed` events record the serving provider and model, plus a `failover` list such as `openai:gpt-4.1-mini:unavailable`.

## Limitations

- Breaker state is per process. Each API or worker process learns provider health on its own; share it through Redis if you need a global view.
- Only generation fails over. Search and embeddings have no fallback.
- A fallback model must support the structured-output format the prompts require. Check each target with a real call (`scripts/gemini_preflight.py` is the pattern) before relying on it.
- Failover is tested with injected providers, not against live vendors.
