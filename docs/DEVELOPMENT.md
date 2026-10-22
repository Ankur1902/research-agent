# Development

Copy `.env.example` to `.env`. Run `docker compose up --build`. Open http://localhost:3000 and register a private organization. Select DEMO when creating a job to exercise approvals, streaming, sources, reports and exports without API keys. The fixture is explicitly synthetic and does not answer real-world questions.

For live web research set the generation provider's API key and `SEARCH_API_KEY`. Hybrid document indexing requires `OPENAI_API_KEY` for its independent embedding adapter; lexical development mode does not. Provider and model must be compatible with structured JSON schemas. Restart API and worker after changing environment configuration.

## Docker-free Gemini development

Create the virtual environment, install `apps/api/requirements.txt`, and install the frontend dependencies with `npm ci` inside `apps/web`. In the root `.env`, set `LLM_PROVIDER=gemini`, your configured `LLM_MODEL`, and `GOOGLE_API_KEY`. Set input/output prices for that model explicitly; accounting uses these configured estimates. Keep secrets in `.env`.

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/local_server.py
```

In another terminal, from `apps/web`:

```powershell
$env:API_INTERNAL_URL = 'http://127.0.0.1:8100'
npm run dev -- --port 3100
```

Open http://localhost:3100. This development entry point uses SQLite at `test-results/e2e-local/browser.sqlite`, a local background queue, and lexical document retrieval. It does not start Redis, Qdrant or Docker, and uploaded documents do not require an embedding key in this mode. DEMO uses no provider calls. LIVE document research calls Gemini; LIVE web research additionally needs `SEARCH_API_KEY`. Restart only this project's API/frontend after changing their configuration. Use available ports and update the development entry point's origin if these ports are already occupied.

The local queue periodically recovers pending research and identifies interrupted runs. It is a development adapter; production continues to use Redis/ARQ. See [upgrade notes](UPGRADE.md) for migration and budget reconciliation details.

## Tooling commands

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

Pytest uses isolated SQLite databases and injected queue/provider adapters. Production queue code uses Redis; the explicit local development entry point uses the in-process adapter. Playwright targets a running stack: `npx playwright install chromium` then `npm run test:e2e`. Live provider calls require credentials and spend money; they are not part of deterministic CI. Provider responses in unit tests must be explicitly injected fixtures, never application fallbacks.

## Changes and migrations

Create a new Alembic revision for schema changes. Do not edit the initial revision after deployment. Prompt files are versioned under `packages/prompts`; rerun evaluation when changing prompts or ranking logic. Never commit secrets, production data, `.env`, or execution artifacts.
