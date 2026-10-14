# Verification — 7 October 2026

Local end-to-end verification completed with isolated test infrastructure. Docker was not invoked. No containers or existing background services were started, stopped, or modified. The temporary API and web servers used ports 8100 and 3100; both were stopped afterward and TCP checks confirmed the ports were closed.

## Results

| Check | Result |
| --- | --- |
| Consolidated Python suite (`python -m pytest -q`) | 72 passed, 1 skipped; final run 51.77 seconds |
| Python lint (`ruff check apps/api scripts tests/security_eval`) | Passed |
| Python type checks (`mypy apps/api/app`) | Passed, 23 source files |
| Formatting check for agent/eval modules and new tests | Passed, 13 files |
| Frontend ESLint | Passed |
| Frontend TypeScript | Passed |
| Next.js optimized production build | Passed |
| Playwright browser journey | 1 passed, 39.1 seconds including runner overhead |
| Security evaluation CLI preflight | 22 cases; 44 logical calls; 7 proposals; zero dispatches |
| Complete security-suite integration | Matched all 22 cases and aggregate call counts using injected providers |
| Persisted agent workflow / saved-trace CLI integration | All 5 shipped workflow scenarios passed |
| Provider transport retry checks | Passed using mock HTTP transport; retry telemetry and bounded errors checked |

The first browser attempt timed out while the Next.js development server compiled the dashboard route. API registration and session requests succeeded. The rerun passed after route compilation. No application failure or relaxed assertion was needed for the passing rerun.

## What ran end to end

The browser connected to the real Next.js UI and FastAPI API through the configured rewrite. It registered a synthetic account, created a project, generated a DEMO plan, approved execution, ran the actual demo worker function, inspected citation evidence, approved the report, downloaded PDF, inspected agent activity, uploaded an approximately 90 KB text document, created a report evaluation, opened provider settings, and signed out.

The isolated API used a real SQLite database and an explicitly synthetic in-process task queue. It did not use Redis or MySQL. Document upload and stored text were verified; semantic indexing was not demonstrated because embeddings and Qdrant were unavailable. The test API disables all provider/search credentials and cannot issue paid model calls. Its code is `scripts/e2e_test_server.py`; it is not a production server entry point.

The workflow integration tests executed the production agent state machine, task routing, arithmetic, verification, report composition, and event persistence with injected structured model responses and retrieval fixtures. They checked plan waiting for approval, one public source with a calculation, document-only retrieval, mixed retrieval, and cancellation before execution. Each persisted trace was then passed to `scripts/trajectory_eval.py` in a separate process. Artifacts are written to ignored `test-results/trajectories/`.

The security-suite integration ran every shipped case through target-response validation, trusted tool policy, expected count/order/argument checks, structured judge validation, redaction, and exact-manifest aggregation. Expected logical calls were 44, proposals were 7, and dispatches were zero. These were fixture provider invocations and injected judge verdicts, not measured live-model security performance. The tests also reject incomplete/mismatched manifests. HTTP transport tests verified successful single attempts, transient retry recovery, permanent rejection without retries or private payload disclosure, and the three-attempt ceiling.

## Fixes and coverage added

- Corrected an import-order lint issue and formatted the new agent/evaluation code.
- Included `tests/security_eval` in default pytest discovery and CI lint coverage.
- Added all-case security harness integration and all-scenario production workflow/CLI integration.
- Added transport retry telemetry regression tests.
- Disabled provider credentials in API test setup so adding a real key later cannot accidentally turn the suite into paid research.
- Added a Docker-free isolated browser-test API and preserved the existing browser assertions.

## Remaining verification gaps

No OpenAI, Anthropic, or Google API key was configured. No live LLM or search request was made. Prompt adherence, judge calibration, provider-specific structured-output compatibility, and live model scores remain unverified. Passing injected-provider tests is not evidence of real-model attack resistance.

The Qdrant integration test was skipped because its required real service was unavailable. Production MySQL, Redis/ARQ scheduling, and Qdrant HTTP behavior were not exercised. The browser used a synthetic queue; the workflow tests used injected search/document evidence. These results are local application and contract verification, not full deployment verification or security certification.

## Reproduction

From the repository root, using the existing environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check apps/api scripts tests/security_eval
.\.venv\Scripts\python.exe -m mypy apps/api/app
.\.venv\Scripts\python.exe scripts/security_eval.py
```

Browser reproduction uses three terminals. Keep ports 3100 and 8100 free. In the root terminal:

```powershell
.\.venv\Scripts\python.exe scripts/e2e_test_server.py
```

In a second terminal at `apps/web`:

```powershell
$env:API_INTERNAL_URL='http://127.0.0.1:8100'
npm exec next dev -- --hostname 127.0.0.1 --port 3100
```

In a third terminal at `apps/web`, after the servers are ready:

```powershell
$env:E2E_BASE_URL='http://localhost:3100'
npm run test:e2e
```

Stop those two test servers afterward. Run `npm run lint`, `npm run typecheck`, and `npm run build` from `apps/web` to repeat frontend quality checks. No Docker command is required for this local verification path.
