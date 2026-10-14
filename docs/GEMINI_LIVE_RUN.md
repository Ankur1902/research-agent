# Live Gemini research — 11 October 2026

Report: http://localhost:3100/research/728f8499-a520-43bf-83a2-691d308332de

Question: **From the uploaded note, list the approval rules and calculate revenue growth from January to February.**

The source is a short synthetic note uploaded through the frontend. It states that plans need approval before execution, reports need approval before publication, and fictional monthly revenue increased from 100 USD to 125 USD. Gemini produced a cited report and the deterministic calculator returned **25% growth**.

| Measurement | Observed |
| --- | ---: |
| Total time from job creation to draft | 44.85 seconds |
| Agent processing windows | 22.22 seconds |
| Plan approval wait | 22.60 seconds |
| Gemini calls | 4 |
| Tool calls | 3 |

| Agent | Model | Provider latency | Input / output tokens |
| --- | --- | ---: | ---: |
| Planner | gemini-3.1-flash-lite | 7.94 seconds | 456 / 166 |
| Analyst | gemini-3.1-flash-lite | 6.50 seconds | 807 / 291 |
| Verifier | gemini-3.1-flash-lite | 5.72 seconds | 889 / 23 |
| Writer | gemini-3.1-flash-lite | 1.72 seconds | 764 / 176 |

Tools: document_search twice (approval rules and revenue figures), then calculator with operation=growth_percent and values=[100,125]. Retrieval was tenant-scoped lexical retrieval; no embeddings, web search, or webpage fetch were used. The local API uses SQLite and a development queue, with real Gemini calls. No Docker command was run and no credential was printed.

The frontend now shows these measured counts, timings, agent/model token totals, and tool arguments through a tenant-protected execution-summary endpoint. Total time includes queueing and human plan approval; processing time excludes approval wait. Final report approval does not change time to draft. These are measurements of one run, not latency guarantees. Historical runs missing timing events display Pending.

The default eval set is six short questions in packages/evals/security/cases.smoke.jsonl: summary, simple arithmetic, calculator selection, zero tool budget, approval bypass, and synthetic-secret protection. It expects 12 logical model calls, one proposed tool call, and zero actual dispatches. The full 22-case dataset remains available explicitly with --dataset packages/evals/security/cases.v1.jsonl.

Initial live smoke results: **5 PASS, 1 INCONCLUSIVE, 0 FAIL, 0 ERROR**. The inconclusive calculator case exposed validation of quoted literal tool-argument fields. Exact matching now checks emitted field strings as well as serialized responses; invented quotes still fail. The targeted live retest passed. The original six-case report is preserved with a nonpassing gate; a fresh six-case rerun after the fix was not performed. Reports: security-eval-results/gemini-smoke-2026-10-11.json and gemini-tool-growth-retest-2026-10-11.json.

Gemini 2.5 Flash-Lite appeared in model discovery but returned 404 on generation. Gemini 3.1 Flash-Lite passed a live structured-output preflight. The complex analyst schema initially returned 400; transport now inlines local schema references and omits size constraints, while original Pydantic validation still enforces bounds and rejects extra fields. See [Google's schema documentation](https://ai.google.dev/gemini-api/docs/structured-output).

Configured token estimates use [Google's published standard text rates](https://ai.google.dev/gemini-api/docs/pricing). This run's estimated cost was approximately $0.0017, not a billing receipt. Model support labels are assessments, not security certifications.

Regression checks: **76 passed, 1 skipped**, Python lint/type checks passed, frontend lint/TypeScript passed. The skipped test requires real Qdrant. Screenshot: docs/live-demo/06-gemini-live-timing.png.
