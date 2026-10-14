# LLM security evaluation

Local tests and browser validation have been executed; see `VERIFICATION_2026-10-07.md` for earlier results. Live Gemini research and a lightweight evaluation set were subsequently executed; see `GEMINI_LIVE_RUN.md` for the latest measured results and limits. Docker was not run.

The target receives a research request and untrusted evidence. It returns an answer and proposed tool intents. A structured LLM judge grades each explicit case check, while deterministic rules independently detect literal canary disclosures, forbidden tools, and invalid tool arguments. A deterministic failure overrides a judge PASS or judge outage. Invalid evidence, missing check coverage, timeouts, and provider failures never pass the gate.

## Files

- `apps/api/app/evaluation/security.py`: typed contracts, dataset validation, bounded target/judge calls, redacted results, and fail-closed aggregate gate.
- `packages/prompts/security_eval/target.v1.txt`: reference research-assistant security policy.
- `packages/prompts/security_eval/judge.v1.txt`: security judge prompt with an explicit trust boundary.
- `packages/evals/security/cases.v1.jsonl`: 22 cases: 11 adversarial cases, 3 benign controls, 6 positive tool-use controls, and 2 authorization/budget controls.
- `apps/api/app/evaluation/contracts.py`: typed expected counts, tool ordering, argument matching, and optional token/latency limits.
- `apps/api/app/agents/tool_policy.py`: trusted catalogs and side-effect-free proposal validation using shared tool schemas.
- `apps/api/app/evaluation/trajectory.py`: saved production trace and report evaluation.
- `packages/evals/workflow/cases.v1.jsonl`: 5 deterministic workflow contracts.
- `scripts/trajectory_eval.py`: offline saved-trace CLI.
- `scripts/security_eval.py`: opt-in CLI, reproducibility hashes, token totals, and JSON report.
- `tests/security_eval/test_evaluator.py`: mocked regression tests outside the API database fixtures.

## Commands for a later authorized test

Run from the repository root using the existing Python environment. These commands are documentation only; they were not executed during implementation.

```powershell
# Mocked tests: no model calls, Docker, database, or research tools.
.\.venv\Scripts\python.exe -m pytest tests/security_eval -q

# Validate configuration and count cases without model calls.
.\.venv\Scripts\python.exe scripts/security_eval.py

# Live LLM evaluation: explicitly billable, sequential, no actual tool execution.
.\.venv\Scripts\python.exe scripts/security_eval.py --live --output security-eval-results/run-001.json

# Repeated evaluation with a custom target policy.
.\.venv\Scripts\python.exe scripts/security_eval.py --live --repetitions 3 --max-model-calls 132 --target-prompt packages/prompts/security_eval/target.v1.txt --output security-eval-results/run-002.json
```

Live mode reuses the existing `LLM_PROVIDER`, `LLM_MODEL`, and corresponding API key configuration. Never put real credentials, private tenant content, or production secrets into the cases. Live payloads are sent to the configured model provider, including the synthetic secret canary. Only use synthetic or explicitly authorized evaluation material.

Default lightweight set: 6 short cases, 12 expected model calls, 1 expected proposal, and zero dispatches. Select the full 22-case set with --dataset packages/evals/security/cases.v1.jsonl (44 calls and 7 proposals). Provider retries are bounded to three HTTP attempts per logical call; the smoke suite's maximum is 36 attempts. Observed attempts remain null when interrupted or unavailable. The call cap is not a monetary budget. Existing output files cannot be overwritten, and incomplete or inconclusive results cannot pass the gate.

## Interpretation and limits

This evaluates the reference prompt and simulated tool proposals, not the running production agent workflow. To assess a different prompt, pass `--target-prompt`; production planning and report schemas differ from this harness's response schema, so testing the full workflow needs a separate adapter and integration checks. No proposed tool is dispatched, no target URL is fetched, and no running project state is changed.

A model refusal is not proof of server-side tenant isolation, RBAC, SSRF prevention, approval enforcement, or budget enforcement. Keep the existing security guard tests and add end-to-end enforcement tests when authorized. A passing score only covers these cases and observations, not a security certification. Literal canary matching will not catch every transformed or encoded disclosure; the semantic judge provides additional assessment but remains fallible. The default judge uses the same configured model as the target, creating correlated-error risk. `SecurityEvaluator` accepts separate target and judge provider instances for independent configurations. Calibrate judge results against human-labeled responses before relying on them as a release signal.

Reports omit raw target responses and persist their SHA-256 hashes, judgments, deterministic failures, expected-versus-observed contract checks, and usage totals. Known canaries are redacted recursively from result text, including tool names and judge explanations. This is not a general-purpose PII scrubber. Treat evaluation reports as sensitive if extending the dataset. Provider errors are stored as fixed codes without exception text. See `EVAL_DESIGN.md` for call semantics and workflow trace contracts.
