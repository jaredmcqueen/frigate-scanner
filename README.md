# frigate-scanner

Discovers publicly exposed [Frigate NVR](https://frigate.video) instances via Shodan, probes each for open access, persists history to SQLite, and serves a live web dashboard.

## Layout

```
src/
  backend/
    run.py                     # CLI entrypoint (run / serve subcommands)
    frigate_scanner/
      search.py                # Shodan queries → host list
      probe.py                 # Async /api/stats probing
      store.py                 # SQLite persistence + scan diff
      report.py                # HTML renderer utilities
      dashboard.py             # FastAPI live dashboard
  frontend/                    # dashboard UI (stub)
```

## Setup

Requires [uv](https://github.com/astral-sh/uv). No virtualenv or `pip install` needed — `uv run` handles dependencies automatically.

Copy `.env.example` to `.env` and add your Shodan API key:

```
SHODAN_API_KEY=your_key_here
```

## Usage

Run a full scan cycle (search → probe → store → terminal summary):

```bash
uv run src/backend/run.py run
```

Key flags for `run`:

| Flag | Default | Description |
|---|---|---|
| `--db PATH` | `frigate.db` | SQLite database path |
| `--workers N` | `20` | Concurrent probe workers |
| `--timeout SECS` | `10.0` | Per-request timeout |

### Dashboard

View the latest scan results as a live card dashboard:

```bash
uv run src/backend/run.py serve
# Opens on http://localhost:8000
```

Key flags for `serve`:

| Flag | Default | Description |
|---|---|---|
| `--db PATH` | `frigate.db` | SQLite database path |
| `--port N` | `8000` | HTTP port |

## Scheduling (daily unattended runs)

### macOS — launchd

A ready-to-use plist template and wrapper script live in [`launchd/`](launchd/) and [`scripts/`](scripts/). Install from the project root:

```bash
# 1. Stamp absolute paths into the plist template and install it
sed \
  -e "s|INSTALL_DIR|$(pwd)|g" \
  -e "s|HOME_DIR|$HOME|g" \
  launchd/com.frigate-scanner.daily.plist \
  > ~/Library/LaunchAgents/com.frigate-scanner.daily.plist

# 2. Make the wrapper executable
chmod +x scripts/run-daily.sh

# 3. Load the agent (starts the daily schedule — no immediate run)
launchctl load ~/Library/LaunchAgents/com.frigate-scanner.daily.plist
```

The agent runs at **06:00 local time** by default. Edit `StartCalendarInterval` in the installed plist to change the time.

Log output appends to:
- `~/Library/Logs/frigate-scanner/scanner.log` — full run output (set by the wrapper)
- `~/Library/Logs/frigate-scanner/launchd.log` — launchd-level stdout/stderr

To run immediately for testing:

```bash
launchctl start com.frigate-scanner.daily
```

To uninstall:

```bash
launchctl unload ~/Library/LaunchAgents/com.frigate-scanner.daily.plist
rm ~/Library/LaunchAgents/com.frigate-scanner.daily.plist
```

### Linux / cron

Add a crontab entry (run `crontab -e`):

```cron
# Run frigate-scanner daily at 06:00
0 6 * * * /path/to/frigate-scanner/scripts/run-daily.sh
```

The wrapper script resolves all paths relative to itself, so no `cd` is needed. Logs go to `~/.local/share/frigate-scanner/` (data) and `~/Library/Logs/frigate-scanner/` (logs). Override with environment variables before calling the script:

```bash
FRIGATE_DATA_DIR=/var/lib/frigate-scanner \
FRIGATE_LOG_DIR=/var/log/frigate-scanner \
  scripts/run-daily.sh
```

See [`src/backend/README.md`](src/backend/README.md) for Docker details.

## Data storage

Results are persisted to `frigate.db` (SQLite). The schema tracks three tables:

- **`scans`** — one row per run (timestamp, hosts scanned, open count)
- **`instances`** — one row per discovered open instance (`first_seen`, `last_seen`)
- **`cameras`** — one row per camera per instance

Each scan computes a diff vs. the previous scan (new / returned / dropped instances and cameras) shown in the terminal summary and in the dashboard.

## Query strategy

The script tries these Shodan queries in order, stopping at the first one that returns results:

1. `http.title:"Live - Frigate"`
2. `http.title:"Frigate"` ← typically matches
3. `title:"Live - Frigate"`
4. `title:"Frigate"`
5. `html:"Live - Frigate"`

## Shodan plan notes

| Plan | Index | Results | Credits |
|---|---|---|---|
| `dev` (free) | Partial | 100/query | 100/mo |
| Membership ($49 one-time) | Full | page through all | 100/mo |
| Small Business ($299/mo) | Full | unlimited | unlimited |

On the `dev` plan the script caps results at 100. With a paid membership (~7 credits for 639 hosts at time of writing) it fetches everything.

The script shows your remaining credits before spending any, and warns you if a full scan would exhaust them.
