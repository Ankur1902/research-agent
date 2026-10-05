# Development

Copy `.env.example` to `.env`. Run `docker compose up --build`. Open http://localhost:3000 and register a private organization. Select DEMO when creating a job to exercise approvals, streaming, sources, reports and exports without API keys. The fixture is explicitly synthetic and does not answer real-world questions.

For live web research set the generation provider's API key and `SEARCH_API_KEY`. For document ingestion set `OPENAI_API_KEY`; embeddings currently use the independent OpenAI adapter. Provider and model must be compatible with structured JSON schemas. Restart API and worker after changing environment configuration.

## Local tooling

```bash
python -m venv .venv
# Activate the virtual environment using your platform's command.
pip install -r apps/api/requirements.txt
pytest -q
ruff check apps/api
mypy apps/api/app
cd apps/web
npm ci
npm run lint
npm run typecheck
npm run build
```

Use `DATABASE_URL=sqlite+aiosqlite:///local.db` only for local development or isolated tests. MySQL is the production adapter. Run `alembic -c apps/api/alembic.ini upgrade head` from the repository root. Start Redis and Qdrant before API / ARQ workers. `PYTHONPATH=apps/api` is required for local Python commands outside pytest.

## Testing

Pytest uses an ephemeral SQLite database and a test-only in-memory queue adapter. Application queue code always uses Redis. Playwright targets the running Compose stack: `npx playwright install chromium` then `npm run test:e2e`. Live provider calls require credentials and spend money; they are not part of deterministic CI. Provider responses in unit tests must be explicitly injected fixtures, never application fallbacks.

## Changes and migrations

Create a new Alembic revision for schema changes. Do not edit the initial revision after deployment. Prompt files are versioned under `packages/prompts`; rerun evaluation when changing prompts or ranking logic. Never commit secrets, production data, `.env`, or execution artifacts.
