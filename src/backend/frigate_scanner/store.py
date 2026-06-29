"""SQLite persistence module — upsert scan results and compute diffs."""

from __future__ import annotations

from pathlib import Path


def record_scan(
    db_path: Path,
    instances: list[dict],
    hosts_scanned: int,
    now: str,
) -> object:
    """Persist instances to SQLite and return a Diff vs. the previous scan."""
    raise NotImplementedError
