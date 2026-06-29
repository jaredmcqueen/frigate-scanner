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

import argparse
import sys


def cmd_run(args: argparse.Namespace) -> None:
    """Orchestrate a full scan cycle: search → probe → store → report."""
    raise NotImplementedError("not yet implemented — see frigate_scanner/ modules")


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
        help="SQLite history database path (default: frigate.db).",
    )
    run_p.add_argument(
        "--out-dir",
        default=".",
        metavar="DIR",
        help="Directory for JSONL and HTML output files (default: current dir).",
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
