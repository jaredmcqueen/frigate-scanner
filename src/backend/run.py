# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "shodan",
#   "python-dotenv",
#   "rich",
#   "httpx",
#   "jinja2",
# ]
# ///

"""Unified Frigate NVR scanner — orchestrates search → probe → store → report."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from frigate_scanner import probe, search
from frigate_scanner.store import Diff, annotate_instances, record_scan


def _print_summary(console: Console, instances: list[dict], diff: Diff) -> None:
    new_count = len(diff.new_instances)
    returned_count = len(diff.returned_instances)
    dropped_count = len(diff.dropped_instances)

    console.rule("[bold cyan]Frigate Scanner — Daily Summary[/bold cyan]")
    console.print(
        f"\n[bold]Open instances:[/bold] {len(instances)}"
        f"   [green]+{new_count} new[/green]"
        f"  [blue]{returned_count} returned[/blue]"
        f"  [red]-{dropped_count} dropped[/red]\n"
    )

    if instances:
        table = Table(show_lines=False, pad_edge=False)
        table.add_column("URL", style="cyan", no_wrap=True)
        table.add_column("CC", width=4)
        table.add_column("Org")
        table.add_column("Cams", justify="right", width=5)
        table.add_column("Status", width=10)

        new_urls = set(diff.new_instances)
        returned_urls = set(diff.returned_instances)

        for r in sorted(instances, key=lambda x: x["url"]):
            url = r["url"]
            if url in new_urls:
                status = "[green]new[/green]"
            elif url in returned_urls:
                status = "[blue]returned[/blue]"
            else:
                status = "known"

            table.add_row(
                url,
                r.get("country_code") or "—",
                r.get("org") or "—",
                str(r.get("probe_camera_count") or 0),
                status,
            )

        console.print(table)

    if diff.dropped_instances:
        console.print("\n[bold red]Dropped since last scan:[/bold red]")
        for d in diff.dropped_instances:
            last = (d.get("last_seen") or "")[:10]
            console.print(
                f"  [red]✗[/red] {d['url']}"
                f"  ({d.get('country_code') or '?'}"
                f", {d.get('org') or '?'}"
                f", last seen {last})"
            )

    console.rule()


def cmd_run(args: argparse.Namespace) -> None:
    """Orchestrate a full scan cycle: search → probe → store → report."""
    load_dotenv()
    api_key = os.environ.get("SHODAN_API_KEY", "")
    if not api_key:
        print(
            "error: SHODAN_API_KEY is not set — copy .env.example to .env and fill it in",
            file=sys.stderr,
        )
        sys.exit(1)

    now = datetime.now(timezone.utc).isoformat()
    console = Console()

    # ── 1. Search ──────────────────────────────────────────────────────────────
    try:
        hosts = search.run(api_key)
    except Exception as exc:
        console.print(f"[red]Search failed:[/red] {exc}")
        sys.exit(1)

    if not hosts:
        console.print("[yellow]No Frigate hosts found on Shodan — nothing to probe.[/yellow]")
        sys.exit(0)

    # ── 2. Probe ───────────────────────────────────────────────────────────────
    open_instances = asyncio.run(probe.run(hosts, workers=args.workers, timeout=args.timeout))

    # ── 3. Store ───────────────────────────────────────────────────────────────
    diff = record_scan(
        Path(args.db),
        open_instances,
        hosts_scanned=len(hosts),
        now=now,
    )
    annotate_instances(open_instances, diff)

    # ── 4. Summary ─────────────────────────────────────────────────────────────
    _print_summary(console, open_instances, diff)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="frigate-scanner",
        description="Discover and probe open Frigate NVR instances via Shodan.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    run_p = subparsers.add_parser("run", help="Run a full scan cycle.")
    run_p.add_argument(
        "--workers",
        type=int,
        default=20,
        metavar="N",
        help="Concurrent probe workers (default: 20).",
    )
    run_p.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        metavar="SECS",
        help="Per-request timeout in seconds (default: 10.0).",
    )
    run_p.add_argument(
        "--db",
        default="frigate.db",
        metavar="PATH",
        help="SQLite database path (default: frigate.db).",
    )
    run_p.add_argument(
        "--out-dir",
        default=".",
        metavar="DIR",
        help="Directory for output files (default: current dir).",
    )
    run_p.add_argument(
        "--jsonl-out",
        default=None,
        metavar="PATH",
        help="Explicit JSONL output path (overrides --out-dir timestamp name).",
    )
    run_p.add_argument(
        "--html-out",
        default=None,
        metavar="PATH",
        help="Explicit HTML output path (overrides --out-dir timestamp name).",
    )
    run_p.set_defaults(func=cmd_run)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except NotImplementedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
