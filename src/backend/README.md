# Backend — Frigate scanner

Two self-contained [uv](https://docs.astral.sh/uv/) scripts (dependencies declared
inline via PEP 723), plus a Dockerfile for eventual containerized daily runs.

## Scripts

| Script           | Purpose                                                                 |
| ---------------- | ----------------------------------------------------------------------- |
| `scan.py`        | Query Shodan for exposed Frigate NVR instances → `frigate_hosts_*.jsonl`. |
| `check_open.py`  | Probe `/api/stats` to find no-auth instances; persist history to SQLite and render an HTML dashboard. |

## Run locally

```bash
# Requires SHODAN_API_KEY (see ../../.env.example)
cd src/backend
uv run scan.py                              # → frigate_hosts_<ts>.jsonl
uv run check_open.py frigate_hosts_*.jsonl  # → frigate.db + frigate_open_<ts>.html
```

## Docker

```bash
docker build -t frigate-scanner src/backend
docker run --rm --env-file .env frigate-scanner
```

## Outputs (all gitignored)

- `frigate_hosts_*.jsonl`, `frigate_open_*.jsonl`, `frigate_open_*.html`
- `frigate.db` — SQLite scan history

## TODO

- Consolidate `scan.py` + `check_open.py` into a single daily entrypoint.
- Add a FastAPI service to serve the dashboard from `frigate.db` (consumed by `src/frontend`).
