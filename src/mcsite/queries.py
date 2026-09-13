"""Every SQL statement the site runs, in one file.

Read-only by construction: no INSERT, UPDATE or DELETE appears here. The site
can never corrupt what the pipeline computed.

Two rules these queries follow, both learned from v1:
  * listings read `product_stats`, never the 763k offers directly — counting
    merchants per page view is what made v1 crawl;
  * an offer is shown only if the pipeline linked it AND the feed still lists it.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

# An offer worth showing. Kept as one string so no query can disagree with another.
_SHOWABLE = "o.linked_status = 'linked' AND o.is_live AND o.product_id IS NOT NULL"

# Category 25 is the pipeline's "not classified yet" sentinel, not a department.
# It must never appear in navigation: a visitor cannot browse a fourre-tout.
UNCLASSIFIED_ID = 25


def _rows(conn: psycopg.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def _row(conn: psycopg.Connection, sql: str, args: tuple = ()) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchone()


# --------------------------------------------------------------------------- home

def categories(conn: psycopg.Connection, min_merchants: int = 2) -> list[dict[str, Any]]:
    """Top-level browsing, with a live count of what is actually comparable."""
    return _rows(conn, """
        SELECT c.id, c.code, c.label_fr,
               count(*) AS n,
               min(s.cheapest) AS from_price
        FROM product p
        JOIN product_stats s ON s.product_id = p.id
        JOIN category c ON c.id = p.category_id
        WHERE s.merchant_count >= %s AND s.cheapest IS NOT NULL AND p.status <> 'merged'
          AND c.id <> 25
        GROUP BY c.id, c.code, c.label_fr
        HAVING count(*) > 0
        ORDER BY count(*) DESC
    """, (min_merchants,))


def totals(conn: psycopg.Connection) -> dict[str, Any]:
    row = _row(conn, """
        SELECT count(*) AS products,
               count(*) FILTER (WHERE merchant_count >= 2) AS comparable,
               sum(offer_count) AS offers
        FROM product_stats
    """)
    return row or {}


# ------------------------------------------------------------------------ listing

def listing(
    conn: psycopg.Connection,
    category_id: int | None,
    min_merchants: int,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """One page of products.

    The window is taken FIRST, then the per-product extras are looked up for the
    24 rows that survived — not for the whole catalogue.
    """
    return _rows(conn, """
        SELECT p.slug, p.brand_code, p.model_display, p.colour_code,
               s.cheapest, s.dearest, s.merchant_count, s.image_url, s.best_title,
               c.label_fr AS category_label
        FROM product p
        JOIN product_stats s ON s.product_id = p.id
        JOIN category c ON c.id = p.category_id
        WHERE (%s::smallint IS NULL OR p.category_id = %s::smallint)
          AND s.merchant_count >= %s
          AND s.cheapest IS NOT NULL
          AND p.status <> 'merged'
        ORDER BY s.merchant_count DESC, s.cheapest
        LIMIT %s OFFSET %s
    """, (category_id, category_id, min_merchants, limit, offset))


def listing_count(conn: psycopg.Connection, category_id: int | None, min_merchants: int) -> int:
    row = _row(conn, """
        SELECT count(*) AS n
        FROM product p JOIN product_stats s ON s.product_id = p.id
        WHERE (%s::smallint IS NULL OR p.category_id = %s::smallint)
          AND s.merchant_count >= %s AND s.cheapest IS NOT NULL AND p.status <> 'merged'
    """, (category_id, category_id, min_merchants))
    return int(row["n"]) if row else 0


# ------------------------------------------------------------------------ product

def product(conn: psycopg.Connection, slug: str) -> dict[str, Any] | None:
    return _row(conn, """
        SELECT p.id, p.brand_code, p.model_display, p.colour_code, p.genre_age,
               p.model_year, p.min_price, p.status, p.slug,
               c.id AS category_id, c.code AS category_code, c.label_fr AS category_label,
               s.merchant_count, s.offer_count, s.cheapest, s.dearest, s.image_url,
               s.best_title
        FROM product p
        JOIN category c ON c.id = p.category_id
        LEFT JOIN product_stats s ON s.product_id = p.id
        WHERE p.slug = %s
    """, (slug,))


def offers(conn: psycopg.Connection, product_id: int) -> list[dict[str, Any]]:
    """The comparison itself, one row per merchant offer, with its size.

    Sorting happens on the page, because the visitor filters by size and the
    cheapest offer changes with the filter.

    Out-of-stock offers are kept — the owner's rule is that nothing disappears,
    it is marked. `in_stock IS NULL` means the merchant said nothing, which is
    not the same as "out of stock" and must not be displayed as one.
    """
    return _rows(conn, f"""
        SELECT DISTINCT ON (o.id)
               m.code AS merchant, o.id AS offer_id, o.price, o.currency, o.in_stock,
               o.deeplink, o.raw_title, o.image_url, o.last_seen,
               coalesce(v.size_code, o.raw_size) AS size_code,
               o.last_seen >= now() - interval '24 hours' AS fresh
        FROM raw_offer o
        JOIN merchant m ON m.id = o.merchant_id
        LEFT JOIN offer_variant_link l ON l.raw_offer_id = o.id
        LEFT JOIN variant v ON v.id = l.variant_id
        WHERE o.product_id = %s AND {_SHOWABLE}
        ORDER BY o.id, v.size_code
    """, (product_id,))


def sizes(conn: psycopg.Connection, product_id: int) -> list[str]:
    rows = _rows(conn, f"""
        SELECT DISTINCT v.size_code
        FROM variant v
        JOIN offer_variant_link l ON l.variant_id = v.id
        JOIN raw_offer o ON o.id = l.raw_offer_id AND {_SHOWABLE}
        WHERE v.product_id = %s
    """, (product_id,))
    return [r["size_code"] for r in rows]


def price_curve(conn: psycopg.Connection, product_id: int, days: int = 180) -> list[dict[str, Any]]:
    """Cheapest price per day. One point means history has only just started."""
    return _rows(conn, """
        SELECT h.observed_on, min(h.price) AS price
        FROM price_history h
        JOIN raw_offer o ON o.id = h.raw_offer_id
        WHERE o.product_id = %s AND h.observed_on >= current_date - %s
        GROUP BY h.observed_on
        ORDER BY h.observed_on
    """, (product_id, days))


def search(conn: psycopg.Connection, term: str, limit: int = 40) -> list[dict[str, Any]]:
    """Deliberately simple for now: brand or model contains the words typed."""
    words = [w for w in term.split() if len(w) > 1][:4]
    if not words:
        return []
    clauses = " AND ".join(
        ["(p.brand_code ILIKE %s OR p.model_display ILIKE %s)"] * len(words)
    )
    args: list[Any] = []
    for w in words:
        args += [f"%{w}%", f"%{w}%"]
    return _rows(conn, f"""
        SELECT p.slug, p.brand_code, p.model_display, p.colour_code,
               s.cheapest, s.merchant_count, s.image_url, s.best_title,
               c.label_fr AS category_label
        FROM product p
        JOIN product_stats s ON s.product_id = p.id
        JOIN category c ON c.id = p.category_id
        WHERE {clauses} AND s.cheapest IS NOT NULL AND p.status <> 'merged'
        ORDER BY s.merchant_count DESC, s.cheapest
        LIMIT %s
    """, (*args, limit))
