.PHONY: bootstrap sync test lint format typecheck security check dev safety-status

bootstrap:
	uv sync --all-groups

sync:
	uv sync --all-groups --frozen

test:
	uv run pytest --cov=quantforge --cov-report=term-missing

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

security:
	uv run python scripts/check_no_secrets.py
	uv run pip-audit --progress-spinner off --cache-dir .tools/pip-audit-cache

check: lint typecheck test security

dev:
	uv run uvicorn quantforge.api.app:create_app --factory --reload

safety-status:
	uv run quantforge safety-status
