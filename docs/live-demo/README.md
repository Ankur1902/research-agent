# Live walkthrough — 11 October 2026

This section describes the earlier DEMO walkthrough. The subsequent real Gemini run and its measured timing are documented in [GEMINI_LIVE_RUN.md](../GEMINI_LIVE_RUN.md).

The local application was started without Docker and demonstrated in the visible Codex browser.

Web: http://localhost:3100
API: http://127.0.0.1:8100
Completed report: http://localhost:3100/research/1180954c-e734-480b-93a5-f1685d2e8b02
Evaluation: http://localhost:3100/evaluations/2f373c13-d516-4cd4-a51f-c70fcd1e7b0e

The walkthrough used an existing synthetic demo account and performed research setup, generated a plan, approved execution, inspected citation S1, approved the resulting report, downloaded its PDF, inspected operational events, and created a report provenance evaluation. The report was left open and signed in for exploration.

This uses the isolated SQLite/in-process-queue server in `scripts/e2e_test_server.py`. All provider credentials are disabled in that server. Research content is explicitly labeled DEMO; no live model, search, Redis, MySQL, or Qdrant service was used. Report metrics describe the synthetic fixture and are not a live-model security score.

Screenshots capture plan approval, citation evidence, the completed report, agent activity, and report evaluation. `researchos-demo-report.pdf` is the actual downloaded export.
