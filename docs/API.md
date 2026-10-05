# API

Interactive OpenAPI: http://localhost:8000/docs. All API routes are versioned `/api/v1`. Errors use FastAPI `detail`, validation errors include field details. Lists support offset / limit where appropriate; limits are capped.

| Routes | Purpose |
|---|---|
| POST auth/register, auth/login, auth/logout; GET auth/me | Cookie session management |
| GET/POST projects; GET projects/{id} | Tenant-scoped projects |
| GET/POST research; GET research/{id} | Background research jobs |
| POST research/{id}/approve, /cancel | Approval state transitions / cancellation |
| GET research/{id}/trace, /sources, /usage | Operational trace, evidence and provider ledger |
| GET research/{id}/events | SSE with sequence ID replay and checkpoints |
| GET research/{id}/export?format=markdown\|html\|pdf\|json | Citation-preserving download |
| GET/POST documents; GET documents/{id}; POST documents/{id}/retry | Upload, parsing and asynchronous embedding/indexing |
| GET/POST evaluations; GET evaluations/{id} | Persisted real report metric computation |
| GET/PATCH settings | Provider readiness and organization defaults |

Requests that change state require the HttpOnly session cookie, `X-CSRF-Token` from auth/me and the configured Origin. Registration and login require Origin but establish the session. RESEARCHER, ADMIN and OWNER can create or approve research. VIEWER cannot mutate resources. Organization settings require OWNER or ADMIN. Cross-tenant IDs consistently return 404.

SSE carries safe JSON event records, never hidden model reasoning. `id` is the sequence and Last-Event-ID supports replay. Named `state` events summarize job state; `checkpoint` closes a stream at approvals and terminal states. The client reconnects after approving a checkpoint.
