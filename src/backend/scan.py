# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "shodan",
#   "python-dotenv",
#   "rich",
# ]
# ///

"""Search Shodan for exposed Frigate NVR instances. Writes JSONL, one host per line."""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import shodan
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

load_dotenv()

QUERIES = [
    'http.title:"Live - Frigate"',
    'http.title:"Frigate"',
    'title:"Live - Frigate"',
    'title:"Frigate"',
    'html:"Live - Frigate"',
]

PAGE_SIZE = 100  # Shodan's fixed page size

console = Console(stderr=True)


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
        console.print(f'[bold]Trying:[/bold] [cyan]{query}[/cyan]')
        try:
            results = api.search(query, page=1)
        except shodan.APIError as e:
            console.print(f"  [red]failed:[/red] {e}")
            continue
        total = results.get("total", 0)
        matches = results.get("matches", [])
        console.print(f"  total={total}\n")
        if total > 0:
            return query, total, matches
    return None, 0, []


def main() -> None:
    api_key = os.environ.get("SHODAN_API_KEY")
    if not api_key:
        console.print("[red]Error:[/red] SHODAN_API_KEY not set in environment or .env")
        sys.exit(1)

    api = shodan.Shodan(api_key)

    try:
        info = api.info()
        plan = info.get("plan", "unknown")
        query_credits = info.get("query_credits", 0)
        console.print(f"\n[dim]Plan:[/dim] {plan}")
        console.print(f"[dim]Query credits remaining:[/dim] {query_credits}")
        console.print(f"[dim]Scan credits remaining:[/dim]  {info.get('scan_credits', '?')}\n")
    except shodan.APIError as e:
        console.print(f"[red]Could not fetch account info:[/red] {e}")
        sys.exit(1)

    # Probe queries — first page counts as 1 credit per query tried.
    query, total, page1_matches = find_query(api)
    if query is None:
        console.print("[yellow]No results across all query variants.[/yellow]")
        sys.exit(0)

    pages_needed = math.ceil(total / PAGE_SIZE)
    # Page 1 already fetched (1 credit spent). Remaining pages each cost 1 more credit.
    credits_remaining_after_probe = query_credits - 1
    credits_for_remaining = pages_needed - 1
    console.print(f"[green]Query:[/green]       {query}")
    console.print(f"[green]Total hosts:[/green] {total}")
    console.print(f"[green]Pages:[/green]       {pages_needed}  ({PAGE_SIZE}/page)")
    console.print(
        f"[green]Credits needed:[/green] {credits_for_remaining} more  "
        f"(you have {credits_remaining_after_probe} left after probe)\n"
    )

    if credits_for_remaining > credits_remaining_after_probe:
        extra_pages_possible = max(credits_remaining_after_probe, 0)
        pages_needed = 1 + extra_pages_possible
        console.print(
            f"[yellow]Warning:[/yellow] Credits will run out before all pages are fetched. "
            f"Will fetch {pages_needed} page(s) (~{pages_needed * PAGE_SIZE} hosts)."
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(f"frigate_hosts_{timestamp}.jsonl")

    written = 0
    with out_path.open("w") as f, Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching pages", total=pages_needed)

        # Write page 1 (already fetched during probing — no extra credit spent).
        for host in page1_matches:
            f.write(json.dumps(shape(host)) + "\n")
            written += 1
        progress.advance(task)

        # Fetch remaining pages.
        for page in range(2, pages_needed + 1):
            try:
                results = api.search(query, page=page)
            except shodan.APIError as e:
                console.print(f"\n[red]Page {page} failed:[/red] {e}")
                break

            for host in results.get("matches", []):
                f.write(json.dumps(shape(host)) + "\n")
                written += 1

            progress.advance(task)

    console.print(f"\n[green]Done.[/green] Wrote {written} hosts → [bold]{out_path}[/bold]")


if __name__ == "__main__":
    main()
