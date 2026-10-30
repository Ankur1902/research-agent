# Deployment

Local: copy `.env.example` to `.env`, then `docker compose up --build`. MySQL migrations run before API and worker. Register at http://localhost:3000, served by the Caddy edge proxy in front of the web container. Use DEMO without credentials; configure provider keys for LIVE. No fixed demo login or plaintext seeded password exists.

```mermaid
flowchart TD
 Client --> ReverseProxy[TLS reverse proxy]
 ReverseProxy --> Web[Next.js]
 Web --> API[FastAPI]
 API --> SQL[MySQL persistent volume]
 API --> Queue[Redis persistent queue]
 Worker[ARQ worker] --> Queue
 Worker --> SQL
 Worker --> Vector[Qdrant persistent volume]
 Worker --> External[Generation / embeddings / search]
```

For production the Compose `edge` service can terminate TLS itself: set `SITE_ADDRESS` to your domain, publish ports 80 and 443 for it, and change its healthcheck to use https. Replace local credentials, set ENVIRONMENT=production, PUBLIC_ORIGIN to the exact HTTPS application origin and AUTH_SECRET to a random value. Use a secrets manager, a private network, TLS termination, authenticated database/cache/vector services, managed backups, readiness checks and a reviewed egress policy. Configure generation input/output and search price estimates for your selected model. Do not expose Redis, MySQL or Qdrant directly to the internet.

Compose is intended for local setup, not a high-availability deployment. See SECURITY.md before public exposure. Run CI and E2E against an isolated test stack; live provider tests should use a dedicated low-budget project.
