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

import typer
from rich.console import Console

from . import __version__
from .feeds import FEEDS, configured_feeds

app = typer.Typer(add_completion=False, help="motocomparo data pipeline")
console = Console()


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
def fetch() -> None:
    """Download each configured feed to the feeds directory. [not implemented]"""
    raise typer.Exit(_todo("fetch"))


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
