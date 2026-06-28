# Backend scanner image.
# Both scripts are self-contained uv scripts (PEP 723 inline metadata),
# so uv resolves their dependencies at run time — no separate lockfile yet.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Cache the uv-managed virtualenvs between runs.
ENV UV_CACHE_DIR=/app/.uv-cache

COPY scan.py check_open.py ./

# SHODAN_API_KEY is supplied at run time (env var or --env-file), never baked in.
# Example:
#   docker run --rm --env-file .env -v "$PWD/data:/app/data" frigate-scanner
#
# Default to a one-shot scan; override the command for check_open.py:
#   docker run --rm --env-file .env frigate-scanner uv run check_open.py <file.jsonl>
CMD ["uv", "run", "scan.py"]
