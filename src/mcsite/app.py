"""The site: routes, and nothing else.

Runs anywhere Python and PostgreSQL run — a laptop today, the VPS tomorrow. It
does not need WordPress, WooCommerce, or a copy of the catalogue: it reads the
pipeline's database directly, which is why there is no `publish` step between
the two and no window during which the site shows yesterday's data.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg_pool import ConnectionPool

from . import labels, queries

load_dotenv()

HERE = Path(__file__).parent
PER_PAGE = 24

pool: ConnectionPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (check .env)")
    # small pool: this is a read-only site, and the box also runs the pipeline
    pool = ConnectionPool(url, min_size=1, max_size=6, kwargs={"autocommit": True})
    pool.wait(timeout=10)
    yield
    pool.close()


app = FastAPI(title="motocomparo v2", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["prix"] = labels.price
templates.env.filters["couleur"] = labels.colour
templates.env.filters["genre"] = labels.genre
templates.env.filters["marchand"] = labels.merchant
templates.env.filters["taille"] = labels.size_display
templates.env.globals["titre_produit"] = labels.product_title


def _nom(row: Any) -> str:
    """The product name: one merchant's own title, verbatim.

    The owner's decision (2026-09-13): show what the merchants wrote, not a name
    rebuilt from it. Which merchant is her order too — Motoblouz, then Speedway,
    La Bécanerie, FC-Moto — and it is applied in `product_stats.best_title`.

    Nothing is stripped here. An earlier version removed the brand, the colour
    and the category noun; it read better on some pages and mangled others
    ("Cuir Swallow T7"), and a title the merchant wrote is at least a title a
    human wrote. `model_display` remains the fallback for a product with no
    usable title at all — it is a fingerprint, so it should show as rarely as
    possible.
    """
    titre = (row.get("best_title") or "").strip()
    return titre or row["model_display"]


templates.env.globals["nom"] = _nom


def _version_css() -> int:
    """Timestamp of the stylesheet, appended to its URL.

    Without it a browser keeps the copy it already has, and a phone is the
    one place where clearing that cache by hand is genuinely awkward. The
    number changes only when the file does, so it is cached normally the
    rest of the time.
    """
    try:
        return int((HERE / "static" / "style.css").stat().st_mtime)
    except OSError:
        return 0


templates.env.globals["version_css"] = _version_css


def _ctx(request: Request, **extra: Any) -> dict[str, Any]:
    with pool.connection() as conn:  # type: ignore[union-attr]
        nav = queries.categories(conn)
    return {"request": request, "nav": nav, **extra}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with pool.connection() as conn:  # type: ignore[union-attr]
        totals = queries.totals(conn)
        featured = queries.listing(conn, None, 2, 12, 0)
    return templates.TemplateResponse(
        request, "home.html", _ctx(request, totals=totals, featured=featured)
    )


@app.get("/c/{code}", response_class=HTMLResponse)
def category(request: Request, code: str, page: int = Query(1, ge=1)):
    with pool.connection() as conn:  # type: ignore[union-attr]
        cats = queries.categories(conn)
        match = next((c for c in cats if c["code"] == code), None)
        if match is None:
            raise HTTPException(404, "Catégorie inconnue")
        offset = (page - 1) * PER_PAGE
        items = queries.listing(conn, match["id"], 2, PER_PAGE, offset)
        total = queries.listing_count(conn, match["id"], 2)
    return templates.TemplateResponse(
        request, "listing.html",
        _ctx(request, titre=match["label_fr"], items=items, total=total,
             page=page, pages=max(1, -(-total // PER_PAGE)), base=f"/c/{code}"),
    )


@app.get("/p/{slug}", response_class=HTMLResponse)
def product(request: Request, slug: str):
    with pool.connection() as conn:  # type: ignore[union-attr]
        p = queries.product(conn, slug)
        if p is None:
            raise HTTPException(404, "Produit inconnu")
        rows = queries.offers(conn, p["id"])
        courbe = queries.price_curve(conn, p["id"])
    # in stock first, then cheapest; an offer with no price goes last
    rows.sort(key=lambda o: (o["in_stock"] is False, o["price"] is None, o["price"] or 0))
    # the sizes offered are whatever the offers actually carry, nothing else
    # filter on the DISPLAYED size: 'TU' is the pipeline's "size unreadable"
    # bucket and renders empty, so it must not become a button of its own.
    tailles = sorted(
        {t for o in rows if (t := labels.size_display(o["size_code"]))},
        key=labels.size_key,
    )
    image = p["image_url"] or next((o["image_url"] for o in rows if o["image_url"]), None)
    return templates.TemplateResponse(
        request, "product.html",
        _ctx(request, p=p, offres=_grouper(rows), tailles=tailles, courbe=courbe,
             image=image, nb_offres=len(rows)),
    )


def _grouper(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse a merchant's sizeless offers at the same price into one row.

    Motoblouz lists the Arai SZ-R four times — XS, S, M and L — and never says
    which. On the page that reads as the same offer repeated four times, which
    looks like a bug and hides that they are four real, different articles. They
    become one row saying so, with the other links kept: dropping them would
    remove real offers from the comparison.

    Only ever groups offers that are genuinely indistinguishable to a visitor:
    same merchant, same price, same stock state, and no size on either side.
    """
    groupes: list[dict[str, Any]] = []
    index: dict[tuple, dict[str, Any]] = {}
    for o in rows:
        if labels.size_display(o["size_code"]):
            groupes.append({**o, "autres": []})
            continue
        cle = (o["merchant"], o["price"], o["in_stock"])
        if cle in index:
            index[cle]["autres"].append(o["deeplink"])
        else:
            tete = {**o, "autres": []}
            index[cle] = tete
            groupes.append(tete)
    return groupes


@app.get("/recherche", response_class=HTMLResponse)
def search(request: Request, q: str = ""):
    with pool.connection() as conn:  # type: ignore[union-attr]
        items = queries.search(conn, q) if q.strip() else []
    return templates.TemplateResponse(
        request, "listing.html",
        _ctx(request, titre=f"Recherche : {q}" if q else "Recherche",
             items=items, total=len(items), page=1, pages=1, base="/recherche"),
    )
