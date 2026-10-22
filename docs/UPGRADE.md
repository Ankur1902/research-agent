# Reliability and evidence upgrade

This release implements the first reliability and evidence improvements from the October 2026 review. It preserves Gemini, the four model stages, plan/report approvals, and the lightweight default evaluation set.

## Changes

- Admission throttling uses the connection's client address before authentication. Rotating a cookie no longer creates another bucket. Forwarded headers are not trusted by this middleware; configure the server's trusted proxy policy deliberately when deploying behind a proxy. Shared client addresses share this ceiling.
- Research creation and approval remain durable database queue intents when Redis is temporarily unavailable. Worker startup and a 30-second recovery task redispatch pending intents. State compare-and-swap suppresses duplicate execution.
- Active phases acquire a persisted 720-second hard lease, longer than the 600-second workflow deadline and 660-second queue timeout. Recovery fails expired work with an explicit interruption event. It preserves evidence, usage and budget receipts. It does **not** automatically resume an interrupted paid operation or promise exactly-once external execution.
- Model and search calls reserve estimated spend in the database before sending a request. Organization admission is serialized with a database write lock. Monthly generation usage, settled search spend and outstanding holds count toward the ceiling. Earlier read snapshots are ended before taking the lock, including on MySQL's default isolation level.
- Input estimates include instructions, question/context, response schema and protocol allowance. Reservations use configured prices and a conservative UTF-8 byte estimate, plus maximum output tokens. Dollar amounts remain estimates, rather than provider invoices. Embeddings are still outside the research ledger.
- Reported model usage is stored even when structured output is invalid. Explicit model request rejections release their hold at zero cost. A timeout or ambiguous server failure retains its hold; generation and Tavily transport do not automatically replay that uncertain request. Explicit throttling responses retain bounded retries.
- Evidence packing selects question-relevant, verbatim windows and reports character offsets/truncation. Lexical candidates are filtered by query terms before the bounded SQL sample. Semantic hits are independently loaded by ID with tenant and indexed-document checks. Both retrieval modes apply the document diversity cap.
- Source recall compares normalized URL identities, preserving query identity and rejecting embedded URL mentions. Saved-trace evaluations now grade recorded tool arguments, with missing observations unable to pass a required argument contract.
- The API image includes the evaluation scripts and writable test artifact/cache directories for its unprivileged user. Docker was not executed during this upgrade.

## Applying the upgrade

For a deployed installation, stop this project's API and worker, and back up its database using the deployment's normal procedure. From the repository root, with the configured database and `PYTHONPATH=apps/api`, run:

```text
python -m alembic -c apps/api/alembic.ini upgrade head
```

Revision `0003` adds the reservation and run-lease tables. Restart the API and worker together afterward. No existing research rows or documents are rewritten. The local development server creates missing tables in its existing SQLite database at startup. This change has not been applied to your running background project.

## Inspecting reserved funds

Authenticated clients can request `GET /api/v1/research/{id}/budget`. The response includes estimated spend, held and available amounts, reservation receipts, and whether a failed/cancelled run requires reconciliation. Access is scoped to the active organization.

Do not clear a held reservation just because its worker stopped. Check the provider's request/billing records first. There is deliberately no automatic expiry or public release endpoint: an uncertain call may already have been billed. Manual reconciliation requires an operator to record confirmed usage and settle the reservation in a controlled database transaction. An operator reconciliation interface is a remaining improvement.

## Verification and limits

Offline verification on 21 October 2026: **100 passed, 1 skipped in 21.17 seconds**. The skipped case requires a real Qdrant service. Ruff and mypy also passed. No Docker or paid provider calls were used.

Regression coverage includes cookie rotation, independent clients, late evidence, URL identity, current-month accounting, simultaneous SQLite reservations, invalid Gemini output usage, explicit rejection versus uncertain outcomes, stale/live leases, queue redispatch and recorded argument grading. The migration chain is tested on temporary SQLite. Existing injected-provider graph tests cover approval through draft reporting without paid calls.

Real MySQL concurrency, Redis/ARQ cron execution, Qdrant, container integration and live-provider behavior require their respective services. This upgrade does not add full stage checkpoint resumption, a semantic accuracy benchmark, scalable full-text indexing, per-user/tenant request buckets, or a report-version/evaluation dashboard. Lexical SQL filtering remains a bounded fallback with substring candidate matching followed by lexical ranking; broad queries can still reach its 10,000-candidate ceiling.
