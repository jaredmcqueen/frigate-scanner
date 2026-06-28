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

```bash
cd src/backend
uv run scan.py                              # → frigate_hosts_<ts>.jsonl
uv run check_open.py frigate_hosts_*.jsonl  # → frigate.db + frigate_open_<ts>.html
```

Output is written to timestamped files in the current directory:

```
frigate_hosts_20260626T143000Z.jsonl
```

Progress and status messages go to **stderr**; the JSONL goes to the file. To also capture stderr:

```bash
uv run scan.py 2>scan.log
```

See [`src/backend/README.md`](src/backend/README.md) for details on the second script and Docker.

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
