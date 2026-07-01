"""Shodan search module — locate exposed Frigate NVR instances."""

from __future__ import annotations

import json
import math
from pathlib import Path

import shodan
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

QUERIES = [
    # Static <title>Frigate</title> from index.html — every recent release uses this;
    # the "Live - Frigate" text seen in a browser tab is set by client-side JS after
    # load and never appears in the raw HTML Shodan indexes, so it's not worth a variant.
    'http.title:"Frigate"',
    # Wider net for hosts where Shodan captured the body but not a clean title match.
    # Pulls in unrelated hosts too (e.g. dashboards that merely link to Frigate), but
    # probe.py verifies every candidate against /api/stats before it's kept.
    'http.html:"Frigate"',
]

PAGE_SIZE = 100  # Shodan's fixed page size

_console = Console(stderr=True)


def build_url(ip: str, port: int, has_ssl: bool) -> str:
    scheme = "https" if (has_ssl or port in (443, 8443, 4443)) else "http"
    host = f"[{ip}]" if ":" in ip else ip
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def shape(host: dict) -> dict:
    ip = host.get("ip_str", "")
    port = host.get("port", 0)
    has_ssl = "ssl" in host
    location = host.get("location", {})

    return {
        "url": build_url(ip, port, has_ssl),
        "ip": ip,
        "port": port,
        "ssl": has_ssl,
        "country": location.get("country_name") or None,
        "country_code": location.get("country_code") or None,
        "city": location.get("city") or None,
        "org": host.get("org") or host.get("isp") or None,
        "hostnames": host.get("hostnames", []),
        "domains": host.get("domains", []),
        "http_title": host.get("http", {}).get("title") or None,
        "last_update": host.get("timestamp") or None,
        "shodan_url": f"https://www.shodan.io/host/{ip}",
    }


def plan_queries(api: shodan.Shodan) -> list[tuple[str, int]]:
    """Return (query, total) for every query variant with at least one result.

    Uses the count endpoint, which is free and doesn't touch query credits,
    so every variant can be checked before spending anything on search pages.
    """
    plans: list[tuple[str, int]] = []
    for query in QUERIES:
        try:
            total = api.count(query).get("total", 0)
        except shodan.APIError as e:
            _console.print(f'[bold]{query}[/bold]  [red]failed:[/red] {e}')
            continue
        _console.print(f'[bold]{query}[/bold]  total={total}')
        if total > 0:
            plans.append((query, total))
    _console.print("")
    return plans


def run(api_key: str, *, jsonl_out: Path | None = None) -> list[dict]:
    """Search Shodan for Frigate hosts; return shaped host records.

    Args:
        api_key: Shodan API key.
        jsonl_out: If set, also write results to this path as JSONL.
    """
    api = shodan.Shodan(api_key)

    try:
        info = api.info()
        plan = info.get("plan", "unknown")
        query_credits = info.get("query_credits", 0)
        _console.print(f"\n[dim]Plan:[/dim] {plan}")
        _console.print(f"[dim]Query credits remaining:[/dim] {query_credits}")
        _console.print(f"[dim]Scan credits remaining:[/dim]  {info.get('scan_credits', '?')}\n")
    except shodan.APIError as e:
        _console.print(f"[red]Could not fetch account info:[/red] {e}")
        raise

    plans = plan_queries(api)
    if not plans:
        _console.print("[yellow]No results across all query variants.[/yellow]")
        return []

    pages_wanted = [(query, math.ceil(total / PAGE_SIZE)) for query, total in plans]
    total_pages_wanted = sum(pages for _, pages in pages_wanted)
    _console.print(f"[green]Queries:[/green]       {len(plans)}")
    _console.print(f"[green]Total hosts:[/green]   {sum(t for _, t in plans)}  (before de-dup)")
    _console.print(f"[green]Pages wanted:[/green]  {total_pages_wanted}  ({PAGE_SIZE}/page)")
    _console.print(f"[green]Credits available:[/green] {query_credits}\n")

    if total_pages_wanted > query_credits:
        _console.print(
            f"[yellow]Warning:[/yellow] Credits will run out before all pages are fetched. "
            f"Will fetch at most {query_credits} page(s) total, spent on queries in order."
        )

    records: dict[tuple[str, int], dict] = {}
    credits_left = query_credits

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=_console,
    ) as progress:
        task = progress.add_task("Fetching pages", total=min(total_pages_wanted, max(query_credits, 0)))

        for query, pages_needed in pages_wanted:
            for page in range(1, pages_needed + 1):
                if credits_left <= 0:
                    break
                try:
                    results = api.search(query, page=page)
                except shodan.APIError as e:
                    _console.print(f"\n[red]{query} page {page} failed:[/red] {e}")
                    break
                credits_left -= 1

                for host in results.get("matches", []):
                    record = shape(host)
                    records.setdefault((record["ip"], record["port"]), record)

                progress.advance(task)
            if credits_left <= 0:
                break

    records_list = list(records.values())
    _console.print(f"\n[green]Done.[/green] Found {len(records_list)} unique hosts.")

    if jsonl_out is not None:
        jsonl_out = Path(jsonl_out)
        jsonl_out.write_text("\n".join(json.dumps(r) for r in records_list) + "\n")
        _console.print(f"Wrote JSONL → [bold]{jsonl_out}[/bold]")

    return records_list
