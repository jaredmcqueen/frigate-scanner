# frigate-scanner

Searches Shodan for publicly exposed [Frigate NVR](https://frigate.video) instances and writes results to JSONL.

## Layout

```
src/
  backend/    # scanner scripts + Dockerfile (scan.py, check_open.py)
  frontend/   # dashboard UI (stub — not scaffolded yet)
```

## Setup

Requires [uv](https://github.com/astral-sh/uv). No virtualenv or `pip install` needed — `uv run` handles dependencies automatically.

Copy `.env.example` to `.env` and add your Shodan API key:

```
SHODAN_API_KEY=your_key_here
```

## Usage

Run a full scan cycle (search → probe → store → summary):

```bash
uv run src/backend/run.py run
```

Key flags:

| Flag | Default | Description |
|---|---|---|
| `--db PATH` | `frigate.db` | SQLite database path |
| `--out-dir DIR` | `.` | Directory for JSONL/HTML output |
| `--workers N` | `20` | Concurrent probe workers |
| `--timeout SECS` | `10.0` | Per-request timeout |

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

## Output format

One JSON object per line. Example record:

```json
{
  "url": "https://50.255.129.34",
  "ip": "50.255.129.34",
  "port": 443,
  "ssl": true,
  "country": "United States",
  "country_code": "US",
  "city": "Danbury",
  "org": "Comcast Cable Communications, LLC",
  "hostnames": ["s34.geekster.com", "frigate.geekster.com"],
  "domains": ["geekster.com"],
  "http_title": "Frigate",
  "last_update": "2026-06-20T14:32:11.123456",
  "shodan_url": "https://www.shodan.io/host/50.255.129.34"
}
```

`url` is a directly clickable link to the exposed instance. `shodan_url` links to the Shodan host detail page.

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
