"""Async HTTP probe module — filter hosts that are open (no auth)."""

from __future__ import annotations


async def run(
    records: list[dict],
    workers: int = 20,
    timeout: float = 10.0,
) -> list[dict]:
    """Probe each host; return only those that respond without authentication."""
    raise NotImplementedError
