# Backend scanner image.
# run.py is a PEP 723 uv script; uv resolves its dependencies at run time.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Cache the uv-managed virtualenvs between runs.
ENV UV_CACHE_DIR=/app/.uv-cache

COPY run.py check_open.py ./
COPY frigate_scanner/ frigate_scanner/

# SHODAN_API_KEY is supplied at run time (env var or --env-file), never baked in.
# Example:
#   docker run --rm --env-file .env -v "$PWD/data:/app/data" frigate-scanner
CMD ["uv", "run", "run.py", "run"]
