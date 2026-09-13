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
def load(
    only: str = typer.Option(None, help="load just this one feed"),
) -> None:
    """Load the downloaded feed CSVs into the `stg_feed_row` staging table."""
    from .load import load_feed

    feeds = configured_feeds()
    if only:
        feeds = [f for f in feeds if f.code == only]
        if not feeds:
            console.print(f"[red]no configured feed named {only!r}[/]")
            raise typer.Exit(1)

    dest = _feeds_dir()
    total = 0
    for f in feeds:
        console.print(f"[bold]{f.code}[/] ...", end=" ")
        try:
            res = load_feed(f, dest / f"{f.code}.csv")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]FAILED[/] {exc}")
            continue
        total += res.rows
        console.print(f"[green]ok[/] {res.rows:,} rows in {res.seconds:.0f}s")

    console.print(f"\n{total:,} rows staged.")


@app.command()
def normalize(
    only: str = typer.Option(None, help="normalize just this one feed"),
    force: bool = typer.Option(
        False, "--force", help="override the retirement circuit-breaker"
    ),
) -> None:
    """Map staged feed rows into typed `raw_offer` records (upsert + freshness)."""
    from .normalize import normalize_feed

    feeds = configured_feeds()
    if only:
        feeds = [f for f in feeds if f.code == only]
        if not feeds:
            console.print(f"[red]no configured feed named {only!r}[/]")
            raise typer.Exit(1)

    for f in feeds:
        console.print(f"[bold]{f.code}[/] ...", end=" ")
        try:
            res = normalize_feed(f, force=force)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]FAILED[/] {exc}")
            continue
        extra = f", {res.gtin_rejected:,} bad GTINs dropped" if res.gtin_rejected else ""
        console.print(
            f"[green]ok[/] {res.upserted:,} offers, {res.retired:,} retired{extra}"
            f" in {res.seconds:.0f}s"
        )


@app.command()
def signature(
    only: str = typer.Option(None, help="signature for just this one feed"),
) -> None:
    """Compute one normalized `offer_signature` per raw offer (no matching yet)."""
    from .feeds import FEEDS
    from .signature import compute_signatures

    mid = None
    if only:
        if only not in FEEDS:
            console.print(f"[red]no feed named {only!r}[/]")
            raise typer.Exit(1)
        mid = FEEDS[only].merchant_id

    console.print("computing signatures ...", end=" ")
    res = compute_signatures(mid)
    console.print(f"[green]ok[/] {res.rows:,} signatures in {res.seconds:.0f}s")


@app.command()
def categorize() -> None:
    """Seed the category taxonomy and classify every merchant category path."""
    from .category import categorize as run_categorize

    console.print("categorizing ...", end=" ")
    res = run_categorize()
    console.print(
        f"[green]ok[/] {res.categories_seeded} categories, "
        f"{res.paths_mapped:,} new paths mapped in {res.seconds:.0f}s"
    )


@app.command()
def match(
    reset: bool = typer.Option(
        False, "--reset", help="undo a previous match run first (dev/re-run only)"
    ),
) -> None:
    """Cluster raw offers into products (GTIN + item_group_id, v1 scope)."""
    from .category import categorize as run_categorize
    from .match import reset_match_state, run_match

    if reset:
        console.print("resetting previous match state ...", end=" ")
        reset_match_state()
        console.print("[green]ok[/]")

    console.print("categorizing ...", end=" ")
    cres = run_categorize()
    console.print(f"[green]ok[/] {cres.paths_mapped:,} paths mapped")

    console.print("matching ...", end=" ")
    res = run_match()
    console.print(
        f"[green]ok[/] {res.products_created:,} products, {res.variants_created:,} variants — "
        f"{res.offers_linked_gtin:,} offers via GTIN, {res.offers_linked_item_group:,} via "
        f"item_group, {res.gtin_conflicts} GTIN conflicts sent to review in {res.seconds:.0f}s"
    )

    # Advisory only: never let a verify-side bug or a real violation turn a
    # successful match run into a failure the user can't unblock. `mcpipe
    # verify` is the command that actually exits non-zero.
    try:
        from .verify import check_match_invariants

        violations = check_match_invariants()
        if violations:
            console.print(
                f"[yellow]verify: {len(violations)} invariant violation(s) found "
                f"— run `mcpipe verify` for details[/]"
            )
        else:
            console.print("verify: [green]0 invariant violations[/]")
    except Exception as exc:  # noqa: BLE001 — reporting only, must not fail the run
        console.print(f"[yellow]verify: skipped ({exc})[/]")


@app.command()
def verify() -> None:
    """Re-check that no `product` mixes category/colour/genre/pack/year/brand
    across its linked offers — a standing regression net for `match`, run
    independently of any specific run."""
    from .verify import check_match_invariants

    console.print("verifying match invariants ...", end=" ")
    violations = check_match_invariants()
    if not violations:
        console.print("[green]ok[/] 0 violations")
        return

    console.print(f"[red]{len(violations)} violation(s)[/]")
    by_field: dict[str, int] = {}
    for v in violations:
        by_field[v.field] = by_field.get(v.field, 0) + 1
    for field, n in sorted(by_field.items(), key=lambda kv: -kv[1]):
        console.print(f"  {field}: {n}")
    for v in violations[:10]:
        console.print(
            f"  product {v.product_id} / {v.field}: {v.distinct_values} "
            f"(offers {v.example_offer_ids[:5]})"
        )
    raise typer.Exit(1)


@app.command()
def enrich() -> None:
    """Correct coarse feed categories from the title (FC-Moto `tops` -> jacket, ...).

    Rebuilds `offer_category_override`; run BEFORE `match` so the corrected
    categories flow into clustering. Colour/size cascades come later.
    """
    from .enrich import enrich_categories

    console.print("enriching categories from titles ...", end=" ")
    res = enrich_categories()
    from .category import CATEGORIES

    labels = {cid: code for cid, _p, code, _l in CATEGORIES}
    console.print(
        f"[green]ok[/] {res.overrides_written:,} overrides from "
        f"{res.candidates_scanned:,} candidates in {res.seconds:.0f}s"
    )
    for cid, n in sorted(res.by_target.items(), key=lambda kv: -kv[1]):
        console.print(f"  -> {labels.get(cid, cid)}: {n:,}")
    console.print("[dim]by rule: " + ", ".join(
        f"{rule} {n:,}" for rule, n in sorted(res.by_rule.items(), key=lambda kv: -kv[1])
    ) + "[/]")

    # Same idea one field over: read what a neighbour already knows. A merchant
    # that does not send a size is not hiding it — another merchant selling the
    # very same barcode has written it down. Must run before `match`, which
    # builds the variants.
    from .enrich import borrow_sizes

    console.print("borrowing missing sizes from the same barcode ...", end=" ")
    borrowed = borrow_sizes()
    console.print(f"[green]ok[/] {borrowed:,} offers given a size")
    console.print("[dim]now run `mcpipe match --reset` to apply.[/]")


@app.command()
def freshness() -> None:
    """Expire stale offers, append today's prices, recompute each product's
    headline price. Run after `match`; safe to re-run."""
    from .freshness import FRESHNESS_WINDOW, run_freshness

    console.print(f"applying freshness (window: {FRESHNESS_WINDOW}) ...", end=" ")
    res = run_freshness()
    console.print(f"[green]ok[/] in {res.seconds:.0f}s")
    console.print(f"  offers fresh: {res.offers_fresh:,}   expired: {res.offers_expired:,}")
    console.print(f"  price history rows written: {res.history_rows:,}")
    console.print(
        f"  headline prices set: {res.prices_set:,}   cleared: {res.prices_cleared:,}"
    )
    console.print(
        f"  products marked stale: {res.products_stale:,}   revived: {res.products_revived:,}"
    )


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
