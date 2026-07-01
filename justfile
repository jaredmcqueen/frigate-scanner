default:
    @just --list

lint:
    uv run ruff check src tests

test:
    uv run pytest

check: lint test
