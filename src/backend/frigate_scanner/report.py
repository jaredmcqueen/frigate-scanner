"""Report module — write JSONL and render HTML output."""

from __future__ import annotations

from pathlib import Path


def write_jsonl(instances: list[dict], path: Path) -> None:
    """Write open instances as newline-delimited JSON."""
    raise NotImplementedError


def write_html(instances: list[dict], scanned_at: str, diff: object, path: Path) -> None:
    """Render the HTML dashboard and write it to path."""
    raise NotImplementedError
