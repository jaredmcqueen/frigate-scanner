"""FastAPI dashboard app — live view of open instances from frigate.db."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from frigate_scanner.report import render_html


def create_app(db_path: Path) -> FastAPI:
    app = FastAPI(title="Frigate Scanner Dashboard")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.OperationalError:
            return "<h1>No scan data yet.</h1>"
        conn.row_factory = sqlite3.Row
        try:
            return _render_dashboard(conn)
        finally:
            conn.close()

    return app


def _render_dashboard(conn: sqlite3.Connection) -> str:
    scan_row = conn.execute(
        "SELECT id, scanned_at FROM scans ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if scan_row is None:
        return "<h1>No scan data yet.</h1>"

    scan_id: int = scan_row["id"]
    scan_ts: str = scan_row["scanned_at"]
    scanned_at: str = scan_ts[:16].replace("T", " ") + " UTC"

    instance_rows = conn.execute(
        "SELECT url, port, country_code, org, frigate_version, camera_count, first_seen "
        "FROM instances WHERE last_scan_id = ?",
        (scan_id,),
    ).fetchall()

    cam_rows = conn.execute(
        "SELECT instance_url, name, first_seen FROM cameras WHERE last_scan_id = ? "
        "ORDER BY instance_url, name",
        (scan_id,),
    ).fetchall()

    cams_by_url: dict[str, list[tuple[str, str]]] = {}
    for c in cam_rows:
        cams_by_url.setdefault(c["instance_url"], []).append((c["name"], c["first_seen"]))

    instances = []
    for r in instance_rows:
        url = r["url"]
        cam_entries = cams_by_url.get(url, [])
        cam_names = [name for name, _ in cam_entries]
        # first_seen == scan_ts means the instance appeared for the first time in this scan
        is_new = r["first_seen"] == scan_ts
        new_cameras = {name for name, first in cam_entries if first == scan_ts}
        instances.append({
            "url": url,
            "port": r["port"],
            "country_code": r["country_code"],
            "org": r["org"],
            "frigate_version": r["frigate_version"],
            "probe_camera_count": r["camera_count"] or 0,
            "probe_cameras": cam_names,
            "frigate_uptime_days": None,
            "is_new": is_new,
            "new_cameras": new_cameras,
        })

    return render_html(instances, scanned_at)
