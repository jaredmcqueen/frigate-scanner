"""Shodan search module — locate exposed Frigate NVR instances."""

from __future__ import annotations

import json
import math
from pathlib import Path

import shodan
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

QUERIES = [
    'http.title:"Live - Frigate"',
    'http.title:"Frigate"',
    'title:"Live - Frigate"',
    'title:"Frigate"',
    'html:"Live - Frigate"',
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


def find_query(api: shodan.Shodan) -> tuple[str, int, list[dict]] | tuple[None, int, list]:
    """Return the first query that has results, the total count, and page-1 matches."""
    for query in QUERIES:
        _console.print(f'[bold]Trying:[/bold] [cyan]{query}[/cyan]')
        try:
            results = api.search(query, page=1)
        except shodan.APIError as e:
            _console.print(f"  [red]failed:[/red] {e}")
            continue
        total = results.get("total", 0)
        matches = results.get("matches", [])
        _console.print(f"  total={total}\n")
        if total > 0:
            return query, total, matches
    return None, 0, []


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

    query, total, page1_matches = find_query(api)
    if query is None:
        _console.print("[yellow]No results across all query variants.[/yellow]")
        return []

    pages_needed = math.ceil(total / PAGE_SIZE)
    credits_remaining_after_probe = query_credits - 1
    credits_for_remaining = pages_needed - 1
    _console.print(f"[green]Query:[/green]       {query}")
    _console.print(f"[green]Total hosts:[/green] {total}")
    _console.print(f"[green]Pages:[/green]       {pages_needed}  ({PAGE_SIZE}/page)")
    _console.print(
        f"[green]Credits needed:[/green] {credits_for_remaining} more  "
        f"(you have {credits_remaining_after_probe} left after probe)\n"
    )

    if credits_for_remaining > credits_remaining_after_probe:
        extra_pages_possible = max(credits_remaining_after_probe, 0)
        pages_needed = 1 + extra_pages_possible
        _console.print(
            f"[yellow]Warning:[/yellow] Credits will run out before all pages are fetched. "
            f"Will fetch {pages_needed} page(s) (~{pages_needed * PAGE_SIZE} hosts)."
        )

    records: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=_console,
    ) as progress:
        task = progress.add_task("Fetching pages", total=pages_needed)

        for host in page1_matches:
            records.append(shape(host))
        progress.advance(task)

        for page in range(2, pages_needed + 1):
            try:
                results = api.search(query, page=page)
            except shodan.APIError as e:
                _console.print(f"\n[red]Page {page} failed:[/red] {e}")
                break

            for host in results.get("matches", []):
                records.append(shape(host))

            progress.advance(task)

    _console.print(f"\n[green]Done.[/green] Found {len(records)} hosts.")

    if jsonl_out is not None:
        jsonl_out = Path(jsonl_out)
        jsonl_out.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        _console.print(f"Wrote JSONL → [bold]{jsonl_out}[/bold]")

    return records
