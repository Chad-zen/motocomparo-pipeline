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


# Same exclusions `match.py`'s GTIN conflict gate uses, so this checks the same
# thing the gate is supposed to guarantee, not a stricter version of it.
#
# genre_age is split into gender ('F'/'H'/'U' — 'U' excluded, genuinely no
# signal) and child_age ('A'/'E' — NOT excluded: 'A' is a *default*, not
# proof, in textnorm.genre_age, so an A/E mix is always worth flagging; this
# was the exact shape of a real bug — see match.py's `conflicts` CTE).
# category_id excludes 25 (`unknown`, the classifier's catch-all).
@dataclass(frozen=True)
class Invariant:
    """One "must not vary within a product" rule.

    `filter_clause` drops rows carrying no signal (a NULL, a sentinel) so they
    cannot look like a disagreement. `tolerance` is the opposite: an SQL
    predicate over the aggregated `distinct_values` that says a variation is
    acceptable after all. Only colour needs one today — see `_COULEURS_COMPATIBLES`.
    """

    field: str
    expr: str
    filter_clause: str | None = None
    tolerance: str | None = None


# Colour is the one field where two different strings are not automatically a
# contradiction, so it carries a tolerance. The expression below is `match.py`'s
# inclusion rule, written the same way on purpose: this module exists to check
# that the result still obeys the gate, and a checker enforcing a STRICTER rule
# than the gate reports failures that are not failures. It fired 2,726 times the
# night the inclusion rule shipped, every one of them an inclusion
# (['BK','BK|MAT'], ['BK-SI','SI']) and not one a real contradiction.
#
# Every pair must be compatible, not merely one "most complete" value: with
# `BK`, `BK|MAT` and `BK|GLO` on one product, a maximal-element test would let
# `BK` bridge matte to gloss, which the owner's rules treat as two products.
_COULEURS_COMPATIBLES = """
    (SELECT bool_and(
            string_to_array(replace(a, '|', '-'), '-')
         @> string_to_array(replace(b, '|', '-'), '-')
         OR string_to_array(replace(b, '|', '-'), '-')
         @> string_to_array(replace(a, '|', '-'), '-'))
     FROM unnest(v.distinct_values) a, unnest(v.distinct_values) b)
"""

_INVARIANTS: list[Invariant] = [
    Invariant("category_id", "s.category_id", "s.category_id != 25"),
    Invariant("primary_colour", "s.primary_colour", "s.primary_colour IS NOT NULL",
              tolerance=_COULEURS_COMPATIBLES),
    Invariant("genre", "left(s.genre_age, 1)", "left(s.genre_age, 1) != 'U'"),
    Invariant("child_age", "right(s.genre_age, 1)"),
    Invariant("is_pack", "s.is_pack"),
    Invariant("model_year", "s.model_year", "s.model_year IS NOT NULL"),
    Invariant("brand_code", "s.brand_code", "s.brand_code IS NOT NULL"),
]


@dataclass
class Violation:
    product_id: int
    field: str
    distinct_values: list
    example_offer_ids: list[int]


def _query(inv: Invariant) -> str:
    filt = f" FILTER (WHERE {inv.filter_clause})" if inv.filter_clause else ""
    # the tolerance needs the aggregate, so it is applied one level out rather
    # than in HAVING, where `distinct_values` does not exist yet
    garde = f"WHERE NOT coalesce({inv.tolerance}, false)" if inv.tolerance else ""
    return f"""
        SELECT v.product_id, v.distinct_values, v.example_offer_ids
        FROM (
            SELECT o.product_id,
                   array_agg(DISTINCT {inv.expr}){filt} AS distinct_values,
                   array_agg(o.id ORDER BY o.id) AS example_offer_ids
            FROM raw_offer o
            JOIN offer_signature s ON s.raw_offer_id = o.id
            WHERE o.product_id IS NOT NULL
              AND (%(product_ids)s::bigint[] IS NULL
                   OR o.product_id = ANY(%(product_ids)s))
            GROUP BY o.product_id
            HAVING count(DISTINCT {inv.expr}){filt} > 1
        ) v
        {garde}
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
            for inv in _INVARIANTS:
                cur.execute(_query(inv), {"product_ids": product_ids})
                for product_id, distinct_values, example_offer_ids in cur.fetchall():
                    violations.append(
                        Violation(product_id, inv.field, distinct_values,
                                  example_offer_ids)
                    )
        return violations
    finally:
        if own_conn:
            conn.close()
