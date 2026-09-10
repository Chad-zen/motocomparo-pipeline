"""Command-line entry point.

Each pipeline stage is its own subcommand so it can be run and inspected in
isolation. `mcpipe run` chains them in order.

    mcpipe fetch          download the merchant feeds
    mcpipe load           CSV -> Postgres staging
    mcpipe normalize      staging -> raw_offer
    mcpipe match          cluster offers into products
    mcpipe enrich         colour / size / category
    mcpipe freshness      expire unseen offers, recompute prices
    mcpipe publish        build + swap the storefront tables (mode-gated)
    mcpipe run            all of the above, in order

Most stages are not implemented yet — this is the skeleton. See docs/roadmap.md.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

from . import __version__
from .feeds import FEEDS, configured_feeds

load_dotenv()  # read .env into the environment before anything looks at it

app = typer.Typer(add_completion=False, help="motocomparo data pipeline")
console = Console()


def _feeds_dir() -> Path:
    return Path(os.environ.get("FEEDS_DIR", "./feeds"))


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB"


@app.command()
def version() -> None:
    """Print the version."""
    console.print(f"mcpipe {__version__}")


@app.command()
def feeds() -> None:
    """List the merchant feeds and whether each one is configured."""
    for f in FEEDS.values():
        state = "[green]configured[/]" if f.url else "[yellow]no URL[/]"
        console.print(
            f"  {f.code:<12} {f.platform:<14} gtin={f.gtin_trust:<10} {state}"
        )
    n = len(configured_feeds())
    console.print(f"\n{n}/{len(FEEDS)} feed(s) configured.")


@app.command()
def fetch(
    only: str = typer.Option(None, help="fetch just this one feed (e.g. 'speedway')"),
    fresh: bool = typer.Option(False, "--fresh", help="re-download even if a recent copy exists"),
) -> None:
    """Download each configured feed to the feeds directory."""
    from .fetch import fetch_feed

    feeds = configured_feeds()
    if only:
        feeds = [f for f in feeds if f.code == only]
        if not feeds:
            console.print(f"[red]no configured feed named {only!r}[/]")
            raise typer.Exit(1)
    if not feeds:
        console.print("[yellow]no feeds configured — set FEED_*_URL in .env[/]")
        raise typer.Exit(1)

    dest = _feeds_dir()
    max_age = None if fresh else 3 * 3600
    total_bytes = 0

    for f in feeds:
        console.print(f"[bold]{f.code}[/] ...", end=" ")
        mark = [0]

        def progress(_code: str, written: int, *, mark: list[int] = mark) -> None:
            if written - mark[0] >= 25 * 1_048_576:
                mark[0] = written
                console.print(_mb(written), end=" ")

        try:
            res = fetch_feed(f, dest, max_age_seconds=max_age, on_progress=progress)
        except Exception as exc:  # noqa: BLE001 — report and keep going
            console.print(f"[red]FAILED[/] {exc}")
            continue

        total_bytes += res.bytes
        if res.from_cache:
            console.print(f"[dim]cached[/] ({_mb(res.bytes)})")
        else:
            console.print(f"[green]ok[/] {_mb(res.bytes)} in {res.seconds:.0f}s")

    console.print(f"\n{_mb(total_bytes)} in {dest}/")


@app.command()
def load() -> None:
    """CSV -> Postgres staging tables. [not implemented]"""
    raise typer.Exit(_todo("load"))


@app.command()
def normalize() -> None:
    """Staging -> raw_offer (one row per merchant SKU). [not implemented]"""
    raise typer.Exit(_todo("normalize"))


@app.command()
def match() -> None:
    """Cluster raw offers into products. [not implemented]"""
    raise typer.Exit(_todo("match"))


@app.command()
def enrich() -> None:
    """Derive colour / size / category. [not implemented]"""
    raise typer.Exit(_todo("enrich"))


@app.command()
def freshness() -> None:
    """Expire unseen offers, recompute min prices, append price history. [not implemented]"""
    raise typer.Exit(_todo("freshness"))


@app.command()
def publish() -> None:
    """Build wp_pc_*_next and swap. Gated by PUBLISH_MODE. [not implemented]"""
    raise typer.Exit(_todo("publish"))


@app.command()
def run() -> None:
    """Run every stage in order. [not implemented]"""
    raise typer.Exit(_todo("run"))


def _todo(stage: str) -> int:
    console.print(f"[yellow]`{stage}` is not implemented yet.[/] See docs/roadmap.md")
    return 1


if __name__ == "__main__":
    app()
