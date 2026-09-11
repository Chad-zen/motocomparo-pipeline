"""Standing invariant checks for `match`'s output.

Three real bugs shipped in `match.py`, each found by a one-off manual audit
after the fact: a GTIN conflict gate too loose on colour/genre, a category
mixed into one product across merchants, a men's and a women's item merged
under one `item_group_id`. Each fix added the missing field to the SQL that
*builds* the match — but nothing kept checking that the *result* still holds
those rules, so a future edit could reintroduce any of them silently.

This module is that check, kept in one place on purpose: every time a new
"must never vary within one product" rule is found, add one entry to
`_INVARIANTS` (and a regression case in `tests/test_match_invariants.py`)
rather than writing another one-off query that gets thrown away after use.

Note on what this can and can't catch: for fields that `match.py`'s linking
SQL already enforces by construction (e.g. `item_group` offers are only
linked when their own recomputed hash equals the unit's), these checks are a
*regression* net — they catch a future edit that removes a field from the
gate, not a bug class nobody has thought of yet. They are not a substitute
for a human (or an agent) re-reasoning about whether the gate is complete.
"""

from __future__ import annotations

from dataclasses import dataclass

from .db import connect

# (field name, SQL expression, optional SQL filter excluding "no signal" rows)
# — same exclusions `match.py`'s GTIN conflict gate uses, so this checks the
# same thing the gate is supposed to guarantee, not a stricter version of it.
#
# genre_age is split into gender ('F'/'H'/'U' — 'U' excluded, genuinely no
# signal) and child_age ('A'/'E' — NOT excluded: 'A' is a *default*, not
# proof, in textnorm.genre_age, so an A/E mix is always worth flagging; this
# was the exact shape of a real bug — see match.py's `conflicts` CTE).
# category_id excludes 25 (`unknown`, the classifier's catch-all).
_INVARIANTS: list[tuple[str, str, str | None]] = [
    ("category_id", "s.category_id", "s.category_id != 25"),
    ("primary_colour", "s.primary_colour", "s.primary_colour IS NOT NULL"),
    ("genre", "left(s.genre_age, 1)", "left(s.genre_age, 1) != 'U'"),
    ("child_age", "right(s.genre_age, 1)", None),
    ("is_pack", "s.is_pack", None),
    ("model_year", "s.model_year", "s.model_year IS NOT NULL"),
    ("brand_code", "s.brand_code", "s.brand_code IS NOT NULL"),
]


@dataclass
class Violation:
    product_id: int
    field: str
    distinct_values: list
    example_offer_ids: list[int]


def _query(expr: str, filter_clause: str | None) -> str:
    filt = f" FILTER (WHERE {filter_clause})" if filter_clause else ""
    return f"""
        SELECT o.product_id,
               array_agg(DISTINCT {expr}){filt} AS distinct_values,
               array_agg(o.id ORDER BY o.id) AS example_offer_ids
        FROM raw_offer o
        JOIN offer_signature s ON s.raw_offer_id = o.id
        WHERE o.product_id IS NOT NULL
          AND (%(product_ids)s::bigint[] IS NULL OR o.product_id = ANY(%(product_ids)s))
        GROUP BY o.product_id
        HAVING count(DISTINCT {expr}){filt} > 1
    """


def check_match_invariants(
    conn=None, product_ids: list[int] | None = None
) -> list[Violation]:
    """Re-verify, from the linked data itself, that no product mixes values on
    any field `match.py`'s gates are meant to keep uniform.

    Pass `conn` to run inside an existing transaction (e.g. a test's
    rollback-only fixture) — the caller owns commit/rollback/close in that
    case. Pass `product_ids` to scope the check to specific products (tests
    must do this, or synthetic rows get judged alongside the real catalogue).
    With neither argument, opens and closes its own read-only connection —
    the shape used by `mcpipe verify` and by `match` reporting on itself.
    """
    own_conn = conn is None
    if own_conn:
        conn = connect()
    try:
        violations = []
        with conn.cursor() as cur:
            for field, expr, filter_clause in _INVARIANTS:
                cur.execute(_query(expr, filter_clause), {"product_ids": product_ids})
                for product_id, distinct_values, example_offer_ids in cur.fetchall():
                    violations.append(
                        Violation(product_id, field, distinct_values, example_offer_ids)
                    )
        return violations
    finally:
        if own_conn:
            conn.close()
