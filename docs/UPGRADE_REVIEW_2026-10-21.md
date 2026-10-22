# ResearchOS upgrade review — 21 October 2026

The highest-value next release should improve reliability, evidence quality, and evaluation coverage. The current foundation already includes typed model outputs, tenant checks, approval gates, real Gemini integration, bounded tools, inspectable evidence, and measured execution summaries. Four LLM roles run in a controlled pipeline; web and knowledge roles are deterministic retrieval workers, rather than additional autonomous LLM agents.

This review did not modify application behavior, start services, run Docker, or make paid provider requests. It added this report and an ignored reproduction harness. Existing regression tests: **76 passed, 1 skipped in 41.09 seconds**. The skipped test needs real Qdrant. Four additional review probes reproduced the findings below using synthetic inputs, in-memory SQLite, and injected infrastructure. A green baseline does not establish that these uncovered paths are correct.

## Findings, ordered by upgrade priority

### 1. P1 — Unauthenticated throttling trusts a caller-controlled cookie

Location: `apps/api/app/main.py:47`.

The limiter uses the raw session cookie as its key before authenticating it. Changing an invalid cookie changes the bucket. With a limit of two requests, a fixed invalid cookie returned 401, 401, 429; rotating invalid cookies returned 401, 401, 401 from the same client. This bypasses the intended pre-authentication throttle and leaves expensive authentication paths exposed to repeated requests.

Upgrade: enforce an independent pre-authentication IP/client bucket that cannot be displaced by arbitrary cookies. Add session/user/tenant buckets only after identity validation. Define a trusted proxy policy before using forwarded addresses, and bound upload and auth concurrency separately. Acceptance: rotating invalid cookies from one client still hits the same limit, legitimate independent clients remain independent, and authenticated users also retain user/tenant ceilings.

### 2. P1 — Worker interruption leaves active runs unable to resume

Location: `apps/api/app/agents/workflow.py:395`; worker retries in `apps/api/app/workers/worker.py`.

The initial compare-and-swap accepts only QUEUED or APPROVED. After an interruption leaves PLANNING, RUNNING, or VERIFICATION persisted, redelivery returns without doing work. The review probe redelivered each active state and observed all three unchanged. Duplicate suppression works for normal delivery, but is not a recovery mechanism for an abandoned run. API commit followed by enqueue is also not transactional, so a process crash between those steps can orphan work.

Upgrade: durable stage checkpoints, expiring worker leases/heartbeats, fencing tokens, and a recovery policy. Persist operation IDs and completed stage outputs so replay does not repeat an already-completed paid request or calculation. Use an outbox for enqueue-after-commit reliability. Ambiguous provider outcomes need explicit reconciliation; do not promise universal exactly-once external calls. Acceptance: interrupt at every stage boundary, reclaim the expired lease, resume from the correct checkpoint, preserve cancellation, and prevent a stale worker from committing over the new owner.

### 3. P1 — CI's container test image cannot run the new trace integration tests

Locations: `docker/api.Dockerfile:5`, `.github/workflows/ci.yml:33`, `apps/api/tests/test_trajectory_integration.py:152`.

The API image copies apps/api and packages but not scripts. The integration test launches scripts/trajectory_eval.py. It also writes test-results under /researchos, while the image switches to a non-root user and only grants ownership of .pytest_cache. The container CI invocation includes this test. Missing script and unwritable artifact directory are independent failures visible from the image/test configuration. Docker was deliberately not run to reproduce them.

Upgrade: package required CLI modules with the test image or install the application/CLI as a package; use pytest tmp_path or a deliberately writable artifact volume. Keep runtime and test images separate if appropriate. Acceptance: the trace CLI integration test passes as the actual non-root image user, and the same required suites are discovered locally and in CI. Validate this in a future authorized container run.

### 4. P1 — Organization budgets are checks, not reservations

Locations: `apps/api/app/agents/workflow.py:34` and `:95`.

Concurrent jobs can read the same recorded spend and both pass admission. The variable named reservation is only a local estimate; it does not hold organization capacity. The organization sum spans all historical jobs, although the preference is named monthly_budget. Input estimates exclude the system prompt and response schema. Provider usage is persisted only after structured parsing succeeds, so a billable response that fails validation can be absent from the ledger. Concurrency overshoot is code-inspected, not demonstrated against a production database in this review.

Upgrade: a transactional spend ledger with reserved and actual amounts, billing-period boundaries, model/version-specific rates, and separate generation/search/embedding entries. Capture usage before validating output content. Reconcile or retain uncertain reservations after transport failures. Acceptance: two concurrent runs cannot reserve more than the remaining tenant ceiling, a new period resets the applicable budget, and invalid structured output does not erase incurred usage.

### 5. P2 — Evidence truncation can remove the answer before analysis

Location: `apps/api/app/agents/workflow.py:282`; retrieval limit in `apps/api/app/rag/pipeline.py:144`.

The analyst and verifier receive the first ten sources and only the first 2,000 characters of each, without a relevance-aware passage selection step. The review stored a notice deadline after character 2,100; the source contained the answer, but the actual analyst input did not. Hybrid retrieval also maps vector hits through an arbitrary SQL subset of 10,000 chunks, so valid top vector hits outside that subset can disappear. The lexical-only branch does not apply the hybrid branch's document diversity cap.

Upgrade: select question-relevant passages before packing the context; retain chunk IDs, page/character offsets, source versions, and explicit truncation metadata. Fetch semantic hits by their IDs with tenant predicates rather than intersecting them with an arbitrary SQL sample. Apply diversity and coverage policies consistently. Acceptance: questions about a passage near the end of a long page remain answerable, an indexed hit beyond the SQL sample remains retrievable, and one long document cannot crowd out all other sources.

### 6. P2 — Expected-source recall can report success for the wrong source

Location: `apps/api/app/evaluation/metrics.py:15`.

The metric uses substring matching on URLs. The review supplied https://other.invalid/?ref=https://target.invalid/report and expected https://target.invalid/report; recall was incorrectly 1.0. Topic coverage is also literal substring presence rather than semantic task completion, and claim support rate simply counts the verifier's statuses.

Upgrade: compare canonical source identities or explicit expected citation/document IDs; keep lexical checks labeled as lexical proxies. Add distinct semantic claim-support and contradiction assessments with human-labeled calibration cases. Acceptance: query-string mentions and lookalike hosts do not count as retrieving the expected source; negated/topic-name-only answers cannot masquerade as semantic coverage.

### 7. P2 — The saved-trace evaluator ignores recorded tool arguments

Location: `apps/api/app/evaluation/trajectory.py:82`.

The production worker now records tool arguments in event.details, but the evaluator still constructs every observed call as (event.agent, None). Argument contracts cannot pass even when the relevant observations exist. Separately, the all-case mock provider reads expected sequences directly and always supplies PASS judgments. That is valid plumbing coverage, but is not independent evidence of agent decisions or judge reliability.

Upgrade: validate and consume recorded argument fields, distinguish absent legacy data from an observed mismatch, and add production-stage evaluation adapters. Keep the six-question smoke set fast. Add a compact held-out negative set for incorrect tool arguments, contradictory sources, fabricated claims, and judge manipulation. Acceptance: correct recorded arguments pass, altered arguments fail, absent arguments remain unmeasured/nonpassing where required, and human-labeled failures are rejected without exposing the answer key to the target.

## Product and architecture upgrades after those fixes

| Upgrade | Concrete result | Constraint |
| --- | --- | --- |
| Evidence-quality gate | Per-claim support/contradiction records, evidence inspection, and at most one targeted follow-up retrieval when a material gap remains | Keep new searches and calls inside the approved budget; do not turn an open-ended agent loop on by default |
| Typed run state and stage interfaces | Separate orchestration, retrieval, verification, accounting, and telemetry from the large Workflow class | Preserve the explicit deterministic graph and approval states; a new framework is optional |
| Durable tool receipts | Show queued, started, succeeded, failed, cancelled, duration, and retry count for each operation | Current tool counts are admitted attempts; do not relabel them as successful executions |
| Evaluation frontend | Select smoke/full datasets, see expected versus observed calls, inspect each failed case, compare prompt hashes | Enforce tenant ownership and retain the original run; a targeted retest must not rewrite its score |
| Project evidence scope | Choose project documents and source freshness; exclude unrelated workspace files | Tenant isolation remains mandatory; project_id currently associates a job but is not a retrieval filter |
| Report history and review | Immutable draft versions, reviewer comments, source snapshots, and clearly marked unapproved exports | Approval should bind the exact report/evidence revision being approved |
| Provider/runtime resilience | Per-stage token budgets, pooled HTTP connections, structured provider errors, retry-after/jitter, circuit breakers | Preserve schema checks and usage accounting; do not add retries that silently duplicate uncertain paid work |
| Practical latency metrics | Queue wait, execution time, approval wait, per-stage p50/p95, cache status, and estimated versus actual spend | Measure improvement with the same lightweight scenarios; the earlier 22.22-second run is one sample |
| Onboarding and documentation | One documented Docker-free Gemini startup path, environment validation, dependency readiness, and a current architecture page | README still leads with Docker and describes embeddings as mandatory, although lexical local mode now exists |

## Suggested delivery sequence

1. **Reliability and protection:** fix rate-limit identity and CI packaging; introduce durable stage ownership and recovery; add transactional spend admission. Ship deterministic regression tests for each fix.
2. **Research quality:** passage selection, evidence/receipt linkage, canonical source metrics, production trace-argument grading, and calibrated verifier cases. Keep the existing short smoke dataset as the default.
3. **User-facing release:** frontend evaluation dashboard, report revisions, project source selection, and complete latency/cost breakdowns. Add one bounded follow-up research cycle only after the quality gate and budget ledger work.

## Reproduction and review boundaries

Ignored harness: test-results/review-2026-10-21/test_review_probes.py. Run using the project Python environment with pytest -q -s. Its four passing assertions confirm that the described problematic behavior exists; they are not acceptance tests declaring that behavior desirable. Promote them into normal regression tests with corrected expectations when implementing fixes.

No provider credentials were printed or used. No deployment, container, running server, membership, or stored user content was changed. Findings about container packaging and cross-job budgeting are static conclusions; live production infrastructure and provider compatibility were not revalidated. This report is an upgrade review, not a completed security certification.
