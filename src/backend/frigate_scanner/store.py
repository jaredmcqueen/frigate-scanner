"""SQLite persistence module — upsert scan results and compute diffs."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

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
    last_scan_id    INTEGER,
    starred         INTEGER NOT NULL DEFAULT 0
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


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a DB's creation (older DBs won't have them)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(instances)")}
    if "starred" not in cols:
        conn.execute("ALTER TABLE instances ADD COLUMN starred INTEGER NOT NULL DEFAULT 0")


def ensure_schema(db_path: Path) -> None:
    """Create tables if missing and migrate an existing DB to the current schema."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def toggle_starred(db_path: Path, url: str) -> bool | None:
    """Flip the starred flag for an instance. Returns the new value, or None if unknown."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        row = conn.execute("SELECT starred FROM instances WHERE url = ?", (url,)).fetchone()
        if row is None:
            return None
        new_value = 0 if row["starred"] else 1
        conn.execute("UPDATE instances SET starred = ? WHERE url = ?", (new_value, url))
        conn.commit()
        return bool(new_value)
    finally:
        conn.close()


@dataclass(frozen=True)
class Diff:
    """Changes between this scan and the previous one."""

    new_instances: list[str] = field(default_factory=list)
    returned_instances: list[str] = field(default_factory=list)
    dropped_instances: list[dict] = field(default_factory=list)
    new_cameras: list[tuple[str, str]] = field(default_factory=list)
    dropped_cameras: list[tuple[str, str]] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.new_instances or self.returned_instances or self.dropped_instances
            or self.new_cameras or self.dropped_cameras
        )


def record_scan(
    db_path: Path,
    instances: list[dict],
    hosts_scanned: int,
    now: str,
) -> Diff:
    """Persist this scan into SQLite and return the diff vs. the previous scan."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)

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
    """Tag records in-place so the HTML renderer can highlight what's new."""
    new_url_set = set(diff.new_instances) | set(diff.returned_instances)
    new_cam_map: dict[str, set[str]] = {}
    for url, name in diff.new_cameras:
        new_cam_map.setdefault(url, set()).add(name)
    for r in instances:
        r["is_new"] = r["url"] in new_url_set
        r["new_cameras"] = new_cam_map.get(r["url"], set())
