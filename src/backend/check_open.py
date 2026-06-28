# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx",
#   "rich",
#   "jinja2",
# ]
# ///

"""Filter a Frigate JSONL scan for instances reachable without authentication.

Frigate is a SPA — the root URL always returns 200 with the HTML shell even
when auth is required (the redirect happens client-side in JS). Instead we
probe /api/stats, which returns actual 401/403 when auth is enabled and
200 + JSON camera data when the instance is open.

Usage:
    uv run check_open.py frigate_hosts_*.jsonl
    uv run check_open.py frigate_hosts_*.jsonl --workers 30 --timeout 10
"""

import argparse
import asyncio
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

console = Console(stderr=True)

TIMEOUT = 10.0
WORKERS = 20
DB_PATH = "frigate.db"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Frigate Open Instances</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }
  h1 { font-size: 1.5rem; font-weight: 700; color: #38bdf8; margin-bottom: 0.25rem; }
  .subtitle { color: #64748b; font-size: 0.875rem; margin-bottom: 2rem; }
  .stats-bar { display: flex; gap: 2rem; margin-bottom: 2rem; padding: 1rem 1.5rem; background: #1e293b; border-radius: 0.75rem; }
  .stat { display: flex; flex-direction: column; }
  .stat-value { font-size: 1.75rem; font-weight: 700; color: #38bdf8; }
  .stat-label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
  .filters { display: flex; gap: 0.75rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
  .filter-btn { padding: 0.375rem 0.875rem; border-radius: 999px; border: 1px solid #334155; background: transparent; color: #94a3b8; cursor: pointer; font-size: 0.8125rem; transition: all 0.15s; }
  .filter-btn:hover, .filter-btn.active { background: #38bdf8; border-color: #38bdf8; color: #0f172a; font-weight: 600; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 1rem; }
  .card { background: #1e293b; border-radius: 0.75rem; padding: 1.25rem; border: 1px solid #334155; transition: border-color 0.15s; }
  .card:hover { border-color: #38bdf8; }
  .card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.875rem; }
  .card-url { font-size: 0.9375rem; font-weight: 600; color: #38bdf8; word-break: break-all; text-decoration: none; }
  .card-url:hover { text-decoration: underline; }
  .badge { font-size: 0.6875rem; padding: 0.2rem 0.5rem; border-radius: 999px; font-weight: 600; white-space: nowrap; }
  .badge-country { background: #1e3a5f; color: #7dd3fc; }
  .badge-new { background: #166534; color: #86efac; }
  .card.is-new { border-color: #22c55e; }
  .cam-chip.is-new { background: #14532d; border-color: #22c55e; color: #86efac; }
  .changes { background: #1e293b; border-radius: 0.75rem; padding: 1.25rem 1.5rem; margin-bottom: 2rem; border: 1px solid #334155; }
  .changes h2 { font-size: 1rem; color: #e2e8f0; margin-bottom: 0.875rem; }
  .change-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; }
  .change-col h3 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }
  .change-col.added h3 { color: #22c55e; }
  .change-col.dropped h3 { color: #f87171; }
  .change-col ul { list-style: none; font-size: 0.8125rem; color: #94a3b8; max-height: 200px; overflow-y: auto; }
  .change-col li { padding: 0.15rem 0; word-break: break-all; }
  .change-col .empty { color: #475569; font-style: italic; }
  .meta { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.875rem; }
  .meta-item { font-size: 0.75rem; color: #64748b; display: flex; align-items: center; gap: 0.3rem; }
  .meta-item strong { color: #94a3b8; }
  .cameras-label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem; }
  .cameras { display: flex; flex-wrap: wrap; gap: 0.375rem; }
  .cam-chip { font-size: 0.75rem; padding: 0.2rem 0.6rem; background: #0f172a; border: 1px solid #334155; border-radius: 999px; color: #94a3b8; }
  .org { font-size: 0.8125rem; color: #64748b; margin-bottom: 0.75rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .hidden { display: none; }
  .search-wrap { flex: 1; min-width: 200px; }
  input[type=search] { width: 100%; padding: 0.375rem 0.875rem; border-radius: 999px; border: 1px solid #334155; background: #1e293b; color: #e2e8f0; font-size: 0.8125rem; outline: none; }
  input[type=search]:focus { border-color: #38bdf8; }
  .count-display { color: #64748b; font-size: 0.8125rem; margin-left: auto; align-self: center; }
  #no-results { display: none; color: #64748b; text-align: center; padding: 3rem; font-size: 0.9375rem; }
</style>
</head>
<body>
<h1>Frigate Open Instances</h1>
<p class="subtitle">Scanned {{ scanned_at }} &mdash; {{ total }} open instances found</p>
<div class="stats-bar">
  <div class="stat"><span class="stat-value">{{ total }}</span><span class="stat-label">Open</span></div>
  <div class="stat"><span class="stat-value">{{ total_cameras }}</span><span class="stat-label">Cameras</span></div>
  <div class="stat"><span class="stat-value">{{ country_count }}</span><span class="stat-label">Countries</span></div>
</div>
{% if diff and diff.has_changes %}
<div class="changes">
  <h2>Changes since last scan</h2>
  <div class="change-grid">
    <div class="change-col added">
      <h3>+ New instances ({{ diff.new_instances|length }})</h3>
      <ul>
        {% for url in diff.new_instances %}<li>{{ url }}</li>{% else %}<li class="empty">none</li>{% endfor %}
      </ul>
    </div>
    <div class="change-col added">
      <h3>↻ Returned ({{ diff.returned_instances|length }})</h3>
      <ul>
        {% for url in diff.returned_instances %}<li>{{ url }}</li>{% else %}<li class="empty">none</li>{% endfor %}
      </ul>
    </div>
    <div class="change-col dropped">
      <h3>− Dropped off ({{ diff.dropped_instances|length }})</h3>
      <ul>
        {% for d in diff.dropped_instances %}<li>{{ d.url }} <span style="color:#475569">[{{ d.country_code or '??' }}]</span></li>{% else %}<li class="empty">none</li>{% endfor %}
      </ul>
    </div>
    <div class="change-col added">
      <h3>+ New cameras ({{ diff.new_cameras|length }})</h3>
      <ul>
        {% for url, name in diff.new_cameras %}<li>{{ name }} <span style="color:#475569">@ {{ url }}</span></li>{% else %}<li class="empty">none</li>{% endfor %}
      </ul>
    </div>
  </div>
</div>
{% endif %}
<div class="filters">
  <div class="search-wrap"><input type="search" id="search" placeholder="Search URL, org, camera…"></div>
  <button class="filter-btn active" data-country="all">All countries</button>
  {% for country in countries %}
  <button class="filter-btn" data-country="{{ country }}">{{ country }}</button>
  {% endfor %}
  <span class="count-display" id="count-display"></span>
</div>
<div class="grid" id="grid">
{% for r in instances %}
  <div class="card{{ ' is-new' if r.is_new else '' }}" data-country="{{ r.country_code or 'XX' }}" data-search="{{ (r.url + ' ' + (r.org or '') + ' ' + ' '.join(r.probe_cameras))|lower }}">
    <div class="card-header">
      <a class="card-url" href="{{ r.url }}" target="_blank" rel="noopener">{{ r.url }}</a>
      <div style="display:flex;gap:0.35rem;flex-wrap:wrap;justify-content:flex-end">
        {% if r.is_new %}<span class="badge badge-new">NEW</span>{% endif %}
        {% if r.country_code %}<span class="badge badge-country">{{ r.country_code }}</span>{% endif %}
      </div>
    </div>
    {% if r.org %}<div class="org">{{ r.org }}</div>{% endif %}
    <div class="meta">
      {% if r.frigate_version %}<span class="meta-item"><strong>v</strong>{{ r.frigate_version }}</span>{% endif %}
      <span class="meta-item"><strong>{{ r.probe_camera_count }}</strong>&nbsp;cam{{ 's' if r.probe_camera_count != 1 else '' }}</span>
      {% if r.frigate_uptime_days is not none %}<span class="meta-item">up {{ r.frigate_uptime_days }}d</span>{% endif %}
      {% if r.port %}<span class="meta-item">:{{ r.port }}</span>{% endif %}
    </div>
    {% if r.probe_cameras %}
    <div class="cameras-label">Cameras</div>
    <div class="cameras">
      {% for cam in r.probe_cameras %}<span class="cam-chip{{ ' is-new' if cam in r.new_cameras else '' }}">{{ cam }}</span>{% endfor %}
    </div>
    {% endif %}
  </div>
{% endfor %}
</div>
<p id="no-results">No instances match your filter.</p>
<script>
const cards = Array.from(document.querySelectorAll('.card'));
const countEl = document.getElementById('count-display');
let activeCountry = 'all';
let searchTerm = '';

function update() {
  let visible = 0;
  cards.forEach(c => {
    const countryOk = activeCountry === 'all' || c.dataset.country === activeCountry;
    const searchOk = !searchTerm || c.dataset.search.includes(searchTerm);
    const show = countryOk && searchOk;
    c.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  countEl.textContent = visible + ' shown';
  document.getElementById('no-results').style.display = visible === 0 ? 'block' : 'none';
}

document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeCountry = btn.dataset.country;
    update();
  });
});

document.getElementById('search').addEventListener('input', e => {
  searchTerm = e.target.value.toLowerCase().trim();
  update();
});

update();
</script>
</body>
</html>
"""


def _extract_frigate_info(stats: dict) -> dict:
    service = stats.get("service", {})
    cameras = stats.get("cameras", {})

    uptime_secs = service.get("uptime")
    uptime_days = round(uptime_secs / 86400, 1) if uptime_secs is not None else None

    camera_details = []
    for name, cam in cameras.items():
        camera_details.append({
            "name": name,
            "fps": cam.get("camera_fps"),
            "detection_enabled": cam.get("detection_enabled"),
        })

    return {
        "frigate_version": service.get("version"),
        "frigate_latest_version": service.get("latest_version"),
        "frigate_uptime_secs": uptime_secs,
        "frigate_uptime_days": uptime_days,
        "frigate_camera_details": camera_details,
    }


SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_at    TEXT    NOT NULL,
    hosts_scanned INTEGER NOT NULL,
    open_count    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS instances (
    url             TEXT PRIMARY KEY,
    ip              TEXT,
    port            INTEGER,
    country         TEXT,
    country_code    TEXT,
    org             TEXT,
    frigate_version TEXT,
    camera_count    INTEGER,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    last_scan_id    INTEGER
);

CREATE TABLE IF NOT EXISTS cameras (
    instance_url TEXT NOT NULL,
    name         TEXT NOT NULL,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    last_scan_id INTEGER,
    PRIMARY KEY (instance_url, name)
);
"""


@dataclass(frozen=True)
class Diff:
    """Changes between this scan and the previous one."""

    new_instances: list[str] = field(default_factory=list)       # never seen before
    returned_instances: list[str] = field(default_factory=list)  # seen before, gone last scan, back now
    dropped_instances: list[dict] = field(default_factory=list)  # online last scan, missing now
    new_cameras: list[tuple[str, str]] = field(default_factory=list)      # (url, name)
    dropped_cameras: list[tuple[str, str]] = field(default_factory=list)  # (url, name)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.new_instances or self.returned_instances or self.dropped_instances
            or self.new_cameras or self.dropped_cameras
        )


def record_scan(db_path: Path, instances: list[dict], hosts_scanned: int, now: str) -> Diff:
    """Persist this scan into SQLite and return the diff vs. the previous scan."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)

        # Snapshot prior state BEFORE we mutate anything.
        prev_scan_id = conn.execute("SELECT MAX(id) AS m FROM scans").fetchone()["m"]
        existing_urls = {r["url"] for r in conn.execute("SELECT url FROM instances")}
        prev_scan_urls = {
            r["url"] for r in conn.execute(
                "SELECT url FROM instances WHERE last_scan_id = ?", (prev_scan_id,)
            )
        } if prev_scan_id is not None else set()
        existing_cams = {
            (r["instance_url"], r["name"]) for r in conn.execute(
                "SELECT instance_url, name FROM cameras"
            )
        }
        prev_scan_cams = {
            (r["instance_url"], r["name"]) for r in conn.execute(
                "SELECT instance_url, name FROM cameras WHERE last_scan_id = ?", (prev_scan_id,)
            )
        } if prev_scan_id is not None else set()

        cur = conn.execute(
            "INSERT INTO scans (scanned_at, hosts_scanned, open_count) VALUES (?, ?, ?)",
            (now, hosts_scanned, len(instances)),
        )
        scan_id = cur.lastrowid

        current_urls: set[str] = set()
        current_cams: set[tuple[str, str]] = set()
        for r in instances:
            url = r["url"]
            current_urls.add(url)
            conn.execute(
                """
                INSERT INTO instances
                    (url, ip, port, country, country_code, org, frigate_version,
                     camera_count, first_seen, last_seen, last_scan_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    ip=excluded.ip, port=excluded.port, country=excluded.country,
                    country_code=excluded.country_code, org=excluded.org,
                    frigate_version=excluded.frigate_version,
                    camera_count=excluded.camera_count,
                    last_seen=excluded.last_seen, last_scan_id=excluded.last_scan_id
                """,
                (
                    url, r.get("ip"), r.get("port"), r.get("country"),
                    r.get("country_code"), r.get("org"), r.get("frigate_version"),
                    r.get("probe_camera_count"), now, now, scan_id,
                ),
            )
            for cam in r.get("probe_cameras", []):
                current_cams.add((url, cam))
                conn.execute(
                    """
                    INSERT INTO cameras (instance_url, name, first_seen, last_seen, last_scan_id)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(instance_url, name) DO UPDATE SET
                        last_seen=excluded.last_seen, last_scan_id=excluded.last_scan_id
                    """,
                    (url, cam, now, now, scan_id),
                )

        new_instances = sorted(current_urls - existing_urls)
        returned_instances = sorted((current_urls & existing_urls) - prev_scan_urls)
        dropped_urls = sorted(prev_scan_urls - current_urls)
        dropped_instances = [
            dict(conn.execute(
                "SELECT url, country_code, org, camera_count, last_seen FROM instances WHERE url = ?",
                (u,),
            ).fetchone())
            for u in dropped_urls
        ]
        new_cameras = sorted(current_cams - existing_cams)
        dropped_cameras = sorted(prev_scan_cams - current_cams)

        conn.commit()
        return Diff(
            new_instances=new_instances,
            returned_instances=returned_instances,
            dropped_instances=dropped_instances,
            new_cameras=new_cameras,
            dropped_cameras=dropped_cameras,
        )
    finally:
        conn.close()


def annotate_instances(instances: list[dict], diff: Diff) -> None:
    """Tag records in-place so the HTML can highlight what's new."""
    new_url_set = set(diff.new_instances) | set(diff.returned_instances)
    new_cam_map: dict[str, set[str]] = {}
    for url, name in diff.new_cameras:
        new_cam_map.setdefault(url, set()).add(name)
    for r in instances:
        r["is_new"] = r["url"] in new_url_set
        r["new_cameras"] = new_cam_map.get(r["url"], set())


async def check(client: httpx.AsyncClient, record: dict) -> dict | None:
    base_url = record["url"].rstrip("/")
    stats_url = f"{base_url}/api/stats"
    try:
        resp = await client.get(stats_url, follow_redirects=True)
    except Exception:
        return None

    if resp.status_code != 200:
        return None

    try:
        stats = resp.json()
    except Exception:
        return None

    if "cameras" not in stats:
        return None

    camera_names = list(stats["cameras"].keys())
    return {
        **record,
        **_extract_frigate_info(stats),
        "probe_status": resp.status_code,
        "probe_stats_url": stats_url,
        "probe_cameras": camera_names,
        "probe_camera_count": len(camera_names),
        "probe_at": datetime.now(timezone.utc).isoformat(),
    }


async def run(records: list[dict], workers: int, timeout: float) -> list[dict]:
    limits = httpx.Limits(max_connections=workers, max_keepalive_connections=workers)
    async with httpx.AsyncClient(
        verify=False,
        timeout=timeout,
        limits=limits,
        headers={"User-Agent": "Mozilla/5.0 (compatible; frigate-scanner/1.0)"},
    ) as client:
        sem = asyncio.Semaphore(workers)
        open_instances: list[dict] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Probing hosts", total=len(records))

            async def probe(record: dict) -> None:
                async with sem:
                    result = await check(client, record)
                    if result:
                        open_instances.append(result)
                    progress.advance(task)

            await asyncio.gather(*(probe(r) for r in records))

    return open_instances


def render_html(instances: list[dict], scanned_at: str, diff: Diff | None = None) -> str:
    from jinja2 import Environment

    env = Environment(autoescape=True)
    tmpl = env.from_string(HTML_TEMPLATE)

    countries = sorted({r.get("country_code") or "XX" for r in instances} - {"XX"})
    total_cameras = sum(r.get("probe_camera_count", 0) for r in instances)

    return tmpl.render(
        instances=instances,
        total=len(instances),
        total_cameras=total_cameras,
        country_count=len(countries),
        countries=countries,
        scanned_at=scanned_at,
        diff=diff,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter Frigate JSONL for open (no-auth) instances")
    parser.add_argument("input", help="JSONL file produced by scan.py")
    parser.add_argument("--workers", type=int, default=WORKERS, help=f"Concurrent requests (default {WORKERS})")
    parser.add_argument("--timeout", type=float, default=TIMEOUT, help=f"Per-request timeout seconds (default {TIMEOUT})")
    parser.add_argument("--db", default=DB_PATH, help=f"SQLite history database (default {DB_PATH})")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        console.print(f"[red]File not found:[/red] {input_path}")
        sys.exit(1)

    records: list[dict] = []
    with input_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    console.print(f"\n[bold]Loaded[/bold] {len(records)} hosts from [cyan]{input_path}[/cyan]")
    console.print(f"[dim]workers={args.workers}  timeout={args.timeout}s[/dim]\n")

    import warnings
    warnings.filterwarnings("ignore")

    open_instances = asyncio.run(run(records, args.workers, args.timeout))

    now_dt = datetime.now(timezone.utc)
    timestamp = now_dt.strftime("%Y%m%dT%H%M%SZ")
    scanned_at = now_dt.strftime("%Y-%m-%d %H:%M UTC")

    # Persist to the history DB and compute the diff vs. the previous scan.
    diff = record_scan(Path(args.db), open_instances, len(records), now_dt.isoformat())
    annotate_instances(open_instances, diff)

    jsonl_path = Path(f"frigate_open_{timestamp}.jsonl")
    with jsonl_path.open("w") as f:
        for record in open_instances:
            f.write(json.dumps(record, default=list) + "\n")

    html_path = Path(f"frigate_open_{timestamp}.html")
    html_path.write_text(render_html(open_instances, scanned_at, diff))

    console.print(f"\n[green]Open (no-auth):[/green] {len(open_instances)} / {len(records)}")
    for r in open_instances:
        cams = r.get("probe_camera_count", "?")
        ver = r.get("frigate_version", "")
        flag = "[bold green]NEW [/bold green]" if r.get("is_new") else ""
        console.print(
            f"  {flag}[bold cyan]{r['url']}[/bold cyan]"
            f"  [{r.get('country_code', '?')}]  {r.get('org', '')}  "
            f"[dim]{cams} cam{'s' if cams != 1 else ''}  v{ver}[/dim]"
        )

    # Diff summary
    console.print(f"\n[bold]Changes since last scan:[/bold]")
    console.print(
        f"  [green]+{len(diff.new_instances)} new[/green]  "
        f"[cyan]↻{len(diff.returned_instances)} returned[/cyan]  "
        f"[red]−{len(diff.dropped_instances)} dropped[/red]  "
        f"[green]+{len(diff.new_cameras)} cameras[/green]  "
        f"[red]−{len(diff.dropped_cameras)} cameras[/red]"
    )
    for d in diff.dropped_instances:
        console.print(f"  [red]−[/red] {d['url']}  [{d.get('country_code') or '??'}]  [dim]last seen {d['last_seen'][:10]}[/dim]")

    console.print(f"\n[green]Done.[/green]")
    console.print(f"  JSON → [bold]{jsonl_path}[/bold]")
    console.print(f"  HTML → [bold]{html_path}[/bold]")
    console.print(f"  DB   → [bold]{args.db}[/bold]")


if __name__ == "__main__":
    main()
