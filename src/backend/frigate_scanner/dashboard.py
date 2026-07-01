"""FastAPI dashboard app — live view of open instances from frigate.db."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse

from frigate_scanner.report import render_cards_fragment, render_detail_fragment, render_shell
from frigate_scanner.store import ensure_schema, toggle_starred

PAGE_SIZE = 20

_TRENDS_STYLE = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }
h1 { font-size: 1.5rem; font-weight: 700; color: #38bdf8; margin-bottom: 0.25rem; }
h2 { font-size: 1rem; font-weight: 600; color: #e2e8f0; margin-bottom: 1rem; }
.subtitle { color: #64748b; font-size: 0.875rem; margin-bottom: 2rem; }
.chart-wrap { background: #1e293b; border-radius: 0.75rem; padding: 1.25rem 1.5rem; margin-bottom: 2rem; border: 1px solid #334155; }
.section { background: #1e293b; border-radius: 0.75rem; padding: 1.25rem 1.5rem; border: 1px solid #334155; }
.trend-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.8125rem; }
th { text-align: left; color: #64748b; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; padding: 0 0 0.5rem; }
td { padding: 0.3rem 0; border-top: 1px solid #1e293b; color: #94a3b8; word-break: break-all; }
td:first-child { color: #e2e8f0; }
.tag { font-size: 0.6875rem; padding: 0.15rem 0.45rem; border-radius: 999px; font-weight: 600; }
.tag-new { background: #166534; color: #86efac; }
.tag-drop { background: #7f1d1d; color: #fca5a5; }
.empty { color: #475569; font-style: italic; font-size: 0.8125rem; }
.stats-bar { display: flex; gap: 2rem; margin-bottom: 2rem; padding: 1rem 1.5rem; background: #1e293b; border-radius: 0.75rem; }
.stat { display: flex; flex-direction: column; }
.stat-value { font-size: 1.75rem; font-weight: 700; color: #38bdf8; }
.stat-label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
"""

_TRENDS_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Frigate Scanner — Trends</title>
<style>{style}</style>
</head>
<body>
<nav style="margin-bottom:1.5rem;display:flex;gap:1rem">
  <a href="/" style="color:#64748b;text-decoration:none;font-size:0.875rem;padding:0.375rem 0.875rem;border-radius:999px;border:1px solid #334155">Live View</a>
  <a href="/trends" style="color:#38bdf8;text-decoration:none;font-size:0.875rem;font-weight:600;padding:0.375rem 0.875rem;border-radius:999px;border:1px solid #38bdf8">Trends</a>
</nav>
<h1>Historical Trends</h1>
<p class="subtitle">{total_scans} scan{plural} &mdash; {first_scan} to {last_scan}</p>
<div class="stats-bar">
  <div class="stat"><span class="stat-value">{total_scans}</span><span class="stat-label">Scans</span></div>
  <div class="stat"><span class="stat-value">{peak_open}</span><span class="stat-label">Peak Open</span></div>
  <div class="stat"><span class="stat-value">{avg_open}</span><span class="stat-label">Avg Open</span></div>
  <div class="stat"><span class="stat-value">{current_open}</span><span class="stat-label">Current</span></div>
</div>
<div class="chart-wrap">
  <h2>Open Instances Over Time</h2>
  {chart_svg}
</div>
<div class="trend-grid">
  <div class="section">
    <h2>New Since Yesterday <span class="tag tag-new">{new_count}</span></h2>
    {new_table}
  </div>
  <div class="section">
    <h2>Dropped Last Scan <span class="tag tag-drop">{dropped_count}</span></h2>
    {dropped_table}
  </div>
  <div class="section">
    <h2>Longest Running (Active)</h2>
    {longevity_table}
  </div>
</div>
</body>
</html>
"""


def _build_svg_chart(scans: list[dict]) -> str:
    """Return an inline SVG polyline chart of open_count over scan history."""
    if len(scans) < 2:
        return '<p class="empty">Need at least 2 scans to plot a chart.</p>'

    W, H = 740, 180
    pad_l, pad_r, pad_t, pad_b = 46, 16, 16, 36
    chart_w = W - pad_l - pad_r
    chart_h = H - pad_t - pad_b
    n = len(scans)

    open_vals = [s["open_count"] for s in scans]
    max_v = max(open_vals) or 1

    def cx(i: int) -> float:
        return pad_l + i * chart_w / (n - 1)

    def cy(v: int) -> float:
        return pad_t + chart_h - (v / max_v) * chart_h

    pts = " ".join(f"{cx(i):.1f},{cy(v):.1f}" for i, v in enumerate(open_vals))

    # filled area under the line
    area_pts = (
        f"{cx(0):.1f},{pad_t + chart_h:.1f} "
        + pts
        + f" {cx(n - 1):.1f},{pad_t + chart_h:.1f}"
    )

    # dots with title tooltips
    dots = "".join(
        f'<circle cx="{cx(i):.1f}" cy="{cy(v):.1f}" r="3" fill="#38bdf8" stroke="#0f172a" stroke-width="1.5">'
        f"<title>{scans[i]['scanned_at'][:16].replace('T', ' ')} UTC\n{v} open</title></circle>"
        for i, v in enumerate(open_vals)
    )

    # y-axis gridlines and labels (4 levels)
    grid = ""
    for pct in [0.0, 0.25, 0.5, 0.75, 1.0]:
        v = int(max_v * pct)
        y = cy(v)
        grid += (
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{W - pad_r}" y2="{y:.1f}"'
            f' stroke="#334155" stroke-width="0.5"/>'
            f'<text x="{pad_l - 6}" y="{y + 4:.1f}" fill="#64748b" font-size="10"'
            f' text-anchor="end" font-family="monospace">{v}</text>'
        )

    # x-axis labels (up to 8 evenly spaced)
    step = max(1, (n - 1) // 7)
    x_labels = ""
    for i in range(0, n, step):
        label = scans[i]["scanned_at"][:10]
        x_labels += (
            f'<text x="{cx(i):.1f}" y="{H - 4}" fill="#64748b" font-size="10"'
            f' text-anchor="middle" font-family="monospace">{label}</text>'
        )
    # always include the last label
    if (n - 1) % step != 0:
        label = scans[-1]["scanned_at"][:10]
        x_labels += (
            f'<text x="{cx(n - 1):.1f}" y="{H - 4}" fill="#64748b" font-size="10"'
            f' text-anchor="middle" font-family="monospace">{label}</text>'
        )

    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"'
        f' style="width:100%;height:auto;display:block">'
        f"{grid}"
        f'<polygon points="{area_pts}" fill="#38bdf8" fill-opacity="0.08"/>'
        f'<polyline points="{pts}" fill="none" stroke="#38bdf8" stroke-width="2"'
        f' stroke-linejoin="round"/>'
        f"{dots}"
        f"{x_labels}"
        f"</svg>"
    )


def _instance_table(rows: list[dict], empty_msg: str) -> str:
    if not rows:
        return f'<p class="empty">{empty_msg}</p>'
    body = ""
    for r in rows:
        ts = (r.get("first_seen") or r.get("last_seen") or "")[:10]
        flag = r.get("country_code") or "??"
        org = (r.get("org") or "")[:30] or "—"
        body += f"<tr><td>{r['url']}</td><td>{flag}</td><td>{org}</td><td>{ts}</td></tr>"
    return (
        "<table><thead><tr><th>URL</th><th>CC</th><th>Org</th><th>Date</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _longevity_table(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">No active instances found.</p>'
    body = ""
    for r in rows:
        first = (r.get("first_seen") or "")[:10]
        cams = r.get("camera_count") or 0
        flag = r.get("country_code") or "??"
        body += f"<tr><td>{r['url']}</td><td>{flag}</td><td>{cams}</td><td>{first}</td></tr>"
    return (
        "<table><thead><tr><th>URL</th><th>CC</th><th>Cams</th><th>First Seen</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _render_trends(conn: sqlite3.Connection) -> str:
    scan_rows = conn.execute(
        "SELECT id, scanned_at, open_count, hosts_scanned FROM scans ORDER BY id"
    ).fetchall()
    if not scan_rows:
        return "<h1>No scan data yet.</h1>"

    scans = [dict(r) for r in scan_rows]
    latest = scans[-1]
    current_scan_id: int = latest["id"]
    prev_scan_id: int | None = scans[-2]["id"] if len(scans) >= 2 else None

    # new since yesterday relative to the latest scan timestamp
    latest_ts = latest["scanned_at"]
    try:
        latest_dt = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))
        if latest_dt.tzinfo is None:
            latest_dt = latest_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        latest_dt = datetime.now(timezone.utc)
    yesterday_iso = (latest_dt - timedelta(hours=24)).isoformat()

    new_rows = conn.execute(
        "SELECT url, country_code, org, first_seen FROM instances "
        "WHERE first_seen >= ? ORDER BY first_seen DESC LIMIT 30",
        (yesterday_iso,),
    ).fetchall()
    new_instances = [dict(r) for r in new_rows]

    # dropped: last_scan_id == prev_scan_id (not updated to current)
    dropped_instances: list[dict] = []
    if prev_scan_id is not None:
        dropped_rows = conn.execute(
            "SELECT url, country_code, org, last_seen FROM instances "
            "WHERE last_scan_id = ? ORDER BY last_seen DESC LIMIT 20",
            (prev_scan_id,),
        ).fetchall()
        dropped_instances = [dict(r) for r in dropped_rows]

    longevity_rows = conn.execute(
        "SELECT url, country_code, org, first_seen, camera_count FROM instances "
        "WHERE last_scan_id = ? ORDER BY first_seen ASC LIMIT 15",
        (current_scan_id,),
    ).fetchall()
    longevity = [dict(r) for r in longevity_rows]

    open_vals = [s["open_count"] for s in scans]
    first_scan = scans[0]["scanned_at"][:10]
    last_scan = latest["scanned_at"][:10]
    n = len(scans)

    html = _TRENDS_TEMPLATE.format(
        style=_TRENDS_STYLE,
        total_scans=n,
        plural="" if n == 1 else "s",
        first_scan=first_scan,
        last_scan=last_scan,
        peak_open=max(open_vals),
        avg_open=round(sum(open_vals) / n),
        current_open=latest["open_count"],
        chart_svg=_build_svg_chart(scans),
        new_count=len(new_instances),
        dropped_count=len(dropped_instances),
        new_table=_instance_table(new_instances, "No new instances in the last 24 h."),
        dropped_table=_instance_table(dropped_instances, "Nothing dropped since last scan."),
        longevity_table=_longevity_table(longevity),
    )
    return html


def _render_cards_fragment(conn: sqlite3.Connection, country: str, q: str, page: int) -> str:
    scan_row = conn.execute(
        "SELECT id, scanned_at FROM scans ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if scan_row is None:
        return "<p>No scan data yet.</p>"

    scan_id: int = scan_row["id"]
    scan_ts: str = scan_row["scanned_at"]
    q_like = f"%{q}%" if q else ""

    totals = conn.execute(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(camera_count), 0) AS cams FROM instances "
        "WHERE last_scan_id = ? "
        "AND (? = '' OR country_code = ?) "
        "AND (? = '' OR url LIKE ? OR COALESCE(org, '') LIKE ?)",
        (scan_id, country, country, q_like, q_like, q_like),
    ).fetchone()
    total: int = totals["cnt"]
    total_cameras: int = totals["cams"]

    offset = (page - 1) * PAGE_SIZE
    instance_rows = conn.execute(
        "SELECT url, port, country, country_code, org, frigate_version, camera_count, "
        "first_seen, last_seen, starred FROM instances "
        "WHERE last_scan_id = ? "
        "AND (? = '' OR country_code = ?) "
        "AND (? = '' OR url LIKE ? OR COALESCE(org, '') LIKE ?) "
        "ORDER BY starred DESC, url LIMIT ? OFFSET ?",
        (scan_id, country, country, q_like, q_like, q_like, PAGE_SIZE, offset),
    ).fetchall()
    instances = [dict(r) for r in instance_rows]

    if instances:
        urls = [inst["url"] for inst in instances]
        placeholders = ",".join("?" * len(urls))
        cam_rows = conn.execute(
            f"SELECT instance_url, name, first_seen, last_seen FROM cameras "
            f"WHERE instance_url IN ({placeholders}) AND last_scan_id = ? "
            f"ORDER BY instance_url, name",
            (*urls, scan_id),
        ).fetchall()
        cams_by_url: dict[str, list[dict]] = {}
        for c in cam_rows:
            cams_by_url.setdefault(c["instance_url"], []).append(
                {"name": c["name"], "first_seen": c["first_seen"], "last_seen": c["last_seen"]}
            )
        for inst in instances:
            inst["cameras"] = cams_by_url.get(inst["url"], [])
            inst["is_new"] = inst["first_seen"] == scan_ts

    country_rows = conn.execute(
        "SELECT DISTINCT country_code FROM instances "
        "WHERE last_scan_id = ? AND country_code IS NOT NULL ORDER BY country_code",
        (scan_id,),
    ).fetchall()
    countries = [r["country_code"] for r in country_rows]

    return render_cards_fragment(
        instances, countries, total, total_cameras, page, PAGE_SIZE, country, q
    )


def _render_instance_detail(conn: sqlite3.Connection, url: str) -> str | None:
    inst_row = conn.execute("SELECT * FROM instances WHERE url = ?", (url,)).fetchone()
    if inst_row is None:
        return None
    instance = dict(inst_row)
    cam_rows = conn.execute(
        "SELECT name, first_seen, last_seen FROM cameras WHERE instance_url = ? ORDER BY name",
        (url,),
    ).fetchall()
    cameras = [dict(r) for r in cam_rows]
    return render_detail_fragment(instance, cameras)


def create_app(db_path: Path) -> FastAPI:
    if db_path.exists():
        ensure_schema(db_path)

    app = FastAPI(title="Frigate Scanner Dashboard")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return render_shell()

    @app.get("/fragments/cards", response_class=HTMLResponse)
    def cards_fragment(country: str = "", q: str = "", page: int = 1) -> str:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.OperationalError:
            return "<p>No scan data yet.</p>"
        conn.row_factory = sqlite3.Row
        try:
            return _render_cards_fragment(conn, country, q, page)
        finally:
            conn.close()

    @app.post("/instance/star", response_class=HTMLResponse)
    def star_instance(url: str, country: str = "", q: str = "") -> Response:
        new_state = toggle_starred(db_path, url)
        if new_state is None:
            return Response(content="Instance not found.", status_code=404)
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.OperationalError:
            return HTMLResponse(content="<p>No scan data yet.</p>")
        conn.row_factory = sqlite3.Row
        try:
            return HTMLResponse(content=_render_cards_fragment(conn, country, q, 1))
        finally:
            conn.close()

    @app.get("/instance", response_class=HTMLResponse)
    def instance_detail(url: str) -> Response:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.OperationalError:
            return Response(content="No scan data yet.", status_code=404)
        conn.row_factory = sqlite3.Row
        try:
            html = _render_instance_detail(conn, url)
            if html is None:
                return Response(content="Instance not found.", status_code=404)
            return HTMLResponse(content=html)
        finally:
            conn.close()

    @app.get("/trends", response_class=HTMLResponse)
    def trends() -> str:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.OperationalError:
            return "<h1>No scan data yet.</h1>"
        conn.row_factory = sqlite3.Row
        try:
            return _render_trends(conn)
        finally:
            conn.close()

    return app
