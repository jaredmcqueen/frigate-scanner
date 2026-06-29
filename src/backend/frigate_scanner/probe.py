"""Async HTTP probe module — filter hosts that are open (no auth)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

_console = Console(stderr=True)


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


async def _check(client: httpx.AsyncClient, record: dict) -> dict | None:
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


async def run(
    records: list[dict],
    workers: int = 20,
    timeout: float = 10.0,
) -> list[dict]:
    """Probe each host; return only those that respond without authentication."""
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
            console=_console,
        ) as progress:
            task = progress.add_task("Probing hosts", total=len(records))

            async def probe(record: dict) -> None:
                async with sem:
                    result = await _check(client, record)
                    if result:
                        open_instances.append(result)
                    progress.advance(task)

            await asyncio.gather(*(probe(r) for r in records))

    return open_instances
