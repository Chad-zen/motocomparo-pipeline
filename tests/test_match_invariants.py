"""Regression tests for `verify.check_match_invariants()`.

Each case reproduces one of the real bugs found in `match.py` by name, using
synthetic rows so the test doesn't depend on (or get confused by) whatever
the live catalogue currently contains. Runs inside a transaction that is
always rolled back — nothing here is ever committed to the dev database.

Requires DATABASE_URL (skipped otherwise, so `pytest -q` stays fast and
offline for everything else).
"""

from __future__ import annotations

import os
import uuid

import pytest

from mcpipe.verify import check_match_invariants

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL (a DB-backed test)"
)


@pytest.fixture()
def db():
    from mcpipe.db import connect

    conn = connect()
    with conn.cursor() as cur:
        # bound the worst case if a test hangs instead of rolling back cleanly
        cur.execute("SET statement_timeout = '5s'")
    try:
        yield conn
    finally:
        conn.rollback()  # never commit synthetic rows
        conn.close()


def _merchant_id(cur) -> int:
    cur.execute("SELECT id FROM merchant LIMIT 1")
    return cur.fetchone()[0]


def _make_product(cur, category_id: int) -> int:
    tag = uuid.uuid4().hex[:12]
    cur.execute(
        """
        INSERT INTO product
            (brand_code, category_id, model_display, colour_code, identity_hash, slug)
        VALUES ('testbrand', %s, 'Test Product', 'unknown', %s, %s)
        RETURNING id
        """,
        (category_id, f"hash-{tag}", f"slug-{tag}"),
    )
    return cur.fetchone()[0]


def _make_offer(
    cur,
    merchant_id: int,
    product_id: int,
    *,
    category_id: int,
    primary_colour: str | None = None,
    genre_age: str = "U-A",
    is_pack: bool = False,
    model_year: int | None = None,
    brand_code: str = "testbrand",
) -> int:
    sku = uuid.uuid4().hex
    cur.execute(
        """
        INSERT INTO raw_offer
            (merchant_id, merchant_sku, raw_title, deeplink, product_id, linked_status)
        VALUES (%s, %s, 'synthetic test offer', 'https://example.test/x', %s, 'linked')
        RETURNING id
        """,
        (merchant_id, sku, product_id),
    )
    offer_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO offer_signature
            (raw_offer_id, category_id, brand_code, primary_colour, genre_age,
             is_pack, model_year, norm_txt)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'synthetic test offer')
        """,
        (offer_id, category_id, brand_code, primary_colour, genre_age, is_pack, model_year),
    )
    return offer_id


def test_clean_product_has_no_violations(db):
    with db.cursor() as cur:
        pid = _make_product(cur, category_id=6)  # jacket
        _make_offer(cur, _merchant_id(cur), pid, category_id=6, primary_colour="BK")
        _make_offer(cur, _merchant_id(cur), pid, category_id=6, primary_colour="BK")

    violations = check_match_invariants(conn=db, product_ids=[pid])
    assert violations == []


def test_category_mix_is_caught(db):
    """Bug #2: FC-Moto's coarse 'tops' category linked alongside 'jacket'."""
    with db.cursor() as cur:
        mid = _merchant_id(cur)
        pid = _make_product(cur, category_id=6)
        _make_offer(cur, mid, pid, category_id=6)  # jacket
        _make_offer(cur, mid, pid, category_id=23)  # apparel_casual

    violations = check_match_invariants(conn=db, product_ids=[pid])
    assert any(v.field == "category_id" for v in violations)


def test_gender_mix_is_caught(db):
    """Bug #3: a men's and a women's item merged under one item_group_id."""
    with db.cursor() as cur:
        mid = _merchant_id(cur)
        pid = _make_product(cur, category_id=11)  # protection
        _make_offer(cur, mid, pid, category_id=11, genre_age="F-A")  # women's
        _make_offer(cur, mid, pid, category_id=11, genre_age="H-A")  # men's

    violations = check_match_invariants(conn=db, product_ids=[pid])
    assert any(v.field == "genre" for v in violations)


def test_child_age_mix_is_caught(db):
    """Bug #5: `^U-` excluded 'U-E' (unisex-child) along with 'U-A', so an
    adult item could merge with its own child edition (real example: an
    adult visor merged with the same visor's "ENFANT" listing)."""
    with db.cursor() as cur:
        mid = _merchant_id(cur)
        pid = _make_product(cur, category_id=1)  # helmet
        _make_offer(cur, mid, pid, category_id=1, genre_age="U-A")  # adult
        _make_offer(cur, mid, pid, category_id=1, genre_age="U-E")  # child

    violations = check_match_invariants(conn=db, product_ids=[pid])
    assert any(v.field == "child_age" for v in violations)


def test_pack_mix_is_caught(db):
    with db.cursor() as cur:
        mid = _merchant_id(cur)
        pid = _make_product(cur, category_id=6)
        _make_offer(cur, mid, pid, category_id=6, is_pack=False)
        _make_offer(cur, mid, pid, category_id=6, is_pack=True)

    violations = check_match_invariants(conn=db, product_ids=[pid])
    assert any(v.field == "is_pack" for v in violations)


def test_year_mix_is_caught(db):
    """Bug #4b: two different model-year editions (e.g. 2023 vs 2026) merged
    when the GTIN 'representative' that won the tiebreak lacked year data."""
    with db.cursor() as cur:
        mid = _merchant_id(cur)
        pid = _make_product(cur, category_id=6)
        _make_offer(cur, mid, pid, category_id=6, model_year=2023)
        _make_offer(cur, mid, pid, category_id=6, model_year=2026)

    violations = check_match_invariants(conn=db, product_ids=[pid])
    assert any(v.field == "model_year" for v in violations)


def test_colour_mix_is_caught(db):
    """Bug #4a: 13 real colourways of one RST suit collapsed onto one
    product when the representative offer never stated a colour."""
    with db.cursor() as cur:
        mid = _merchant_id(cur)
        pid = _make_product(cur, category_id=6)
        _make_offer(cur, mid, pid, category_id=6, primary_colour="BK")
        _make_offer(cur, mid, pid, category_id=6, primary_colour="BK-RD")

    violations = check_match_invariants(conn=db, product_ids=[pid])
    assert any(v.field == "primary_colour" for v in violations)


def test_unknown_category_does_not_false_positive(db):
    """Bug #6: one offer landing in the classifier's 'unknown' catch-all
    (category 25) was blocking an otherwise-clean merge for no reason —
    5,005 GTIN groups were quarantined solely for this in live data."""
    with db.cursor() as cur:
        mid = _merchant_id(cur)
        pid = _make_product(cur, category_id=6)
        _make_offer(cur, mid, pid, category_id=6)
        _make_offer(cur, mid, pid, category_id=25)  # unknown

    violations = check_match_invariants(conn=db, product_ids=[pid])
    assert violations == []


def test_brand_mix_is_caught(db):
    """The GTIN conflict gate didn't check brand_code until this review."""
    with db.cursor() as cur:
        mid = _merchant_id(cur)
        pid = _make_product(cur, category_id=6)
        _make_offer(cur, mid, pid, category_id=6, brand_code="alpinestars")
        _make_offer(cur, mid, pid, category_id=6, brand_code="dainese")

    violations = check_match_invariants(conn=db, product_ids=[pid])
    assert any(v.field == "brand_code" for v in violations)


def test_missing_signal_does_not_false_positive(db):
    """One offer with no colour info must not be flagged against another that
    has one — `match.py`'s gate deliberately treats a missing signal as
    "no evidence of conflict", not as a mismatch; the check must agree."""
    with db.cursor() as cur:
        mid = _merchant_id(cur)
        pid = _make_product(cur, category_id=6)
        _make_offer(cur, mid, pid, category_id=6, primary_colour="BK")
        _make_offer(cur, mid, pid, category_id=6, primary_colour=None)

    violations = check_match_invariants(conn=db, product_ids=[pid])
    assert violations == []


def test_scoping_ignores_other_products(db):
    """A real, unrelated violation elsewhere must not leak into a scoped check."""
    with db.cursor() as cur:
        mid = _merchant_id(cur)
        clean_pid = _make_product(cur, category_id=6)
        _make_offer(cur, mid, clean_pid, category_id=6)
        _make_offer(cur, mid, clean_pid, category_id=6)

        dirty_pid = _make_product(cur, category_id=6)
        _make_offer(cur, mid, dirty_pid, category_id=6)
        _make_offer(cur, mid, dirty_pid, category_id=23)

    violations = check_match_invariants(conn=db, product_ids=[clean_pid])
    assert violations == []
