.PHONY: test eval lint typecheck security build up
test:
	python -m pytest -q
eval:
	python scripts/evaluate.py
lint:
	python -m ruff check apps/api scripts
	cd apps/web && npm run lint
typecheck:
	python -m mypy apps/api/app
	cd apps/web && npm run typecheck
security:
	python -m pytest apps/api/tests/test_security.py -q
build:
	cd apps/web && npm run build
up:
	docker compose up --build
