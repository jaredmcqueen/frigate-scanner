default:
    @just --list

lint:
    uv run ruff check src tests

test:
    uv run pytest

check: lint test

scan:
    uv run src/backend/run.py run

serve:
    uv run src/backend/run.py serve
