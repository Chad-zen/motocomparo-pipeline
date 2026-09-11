"""Stage 0 — compute one `offer_signature` per `raw_offer`.

This does no matching. It turns each offer's messy strings into clean, comparable
fields (brand code, colour code, model tokens, size, genre/age, year, pack flag)
so that `match` can compare signatures instead of re-parsing titles every run.

`category_id`, `identity_hash` and `base_sku` are left NULL here — `match` owns
them (base_sku only Motoblouz needs, as a guarded blocking key).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from . import textnorm as tn
from .db import connect

_SIG_COLS = (
    "raw_offer_id",
    "brand_code",
    "brand_known",
    "model_core_ref",
    "model_tokens",
    "model_strength",
    "primary_colour",
    "colour_conf",
    "colour_source",
    "size_code",
    "size_source",
    "genre_age",
    "model_year",
    "base_sku",
    "is_pack",
    "norm_txt",
)


@dataclass
class SignatureResult:
    rows: int
    seconds: float


def _signature_row(o: dict) -> tuple:
    title = o["raw_title"]
    brand_code, brand_known = tn.brand(o["raw_brand"])

    # colour: trust the feed's own field first, fall back to the title
    canon, _bucket, _ = tn.colour(o["raw_color"])
    colour_source = "feed" if canon else "none"
    if not canon:
        canon, _bucket, _ = tn.colour(title)
        colour_source = "title" if canon else "none"
    colour_conf = {"feed": 0.90, "title": 0.55, "none": 0.0}[colour_source]

    size, size_source = tn.size_code(o["raw_size"], title, o["deeplink"], o["raw_mpn"])

    blob = tn.norm_txt(f"{title} {o['raw_category'] or ''}")

    tokens, core_ref, strength = tn.model(title, brand_code, o["raw_color"], o["raw_size"])

    return (
        o["id"],
        brand_code or None,
        brand_known,
        core_ref or None,
        tokens,
        strength,
        canon or None,
        colour_conf,
        colour_source,
        size or None,
        size_source or None,
        tn.genre_age(blob, o["raw_gender"], o["raw_age_group"]),
        tn.model_year(blob),  # title/category only — never the deeplink slug
        None,  # base_sku: deferred to `match` (Motoblouz-only, guarded key)
        tn.is_pack(blob),
        tn.norm_txt(title),
    )


_CREATE_TEMP = """
CREATE TEMP TABLE _sig (
    raw_offer_id   bigint,
    brand_code     text,
    brand_known    boolean,
    model_core_ref text,
    model_tokens   text[],
    model_strength text,
    primary_colour text,
    colour_conf    real,
    colour_source  text,
    size_code      text,
    size_source    text,
    genre_age      text,
    model_year     smallint,
    base_sku       text,
    is_pack        boolean,
    norm_txt       text
) ON COMMIT DROP
"""

_UPSERT = f"""
INSERT INTO offer_signature ({", ".join(_SIG_COLS)}, computed_at)
SELECT {", ".join(_SIG_COLS)}, now() FROM _sig
ON CONFLICT (raw_offer_id) DO UPDATE SET
    brand_code     = EXCLUDED.brand_code,
    brand_known    = EXCLUDED.brand_known,
    model_core_ref = EXCLUDED.model_core_ref,
    model_tokens   = EXCLUDED.model_tokens,
    model_strength = EXCLUDED.model_strength,
    primary_colour = EXCLUDED.primary_colour,
    colour_conf    = EXCLUDED.colour_conf,
    colour_source  = EXCLUDED.colour_source,
    size_code      = EXCLUDED.size_code,
    size_source    = EXCLUDED.size_source,
    genre_age      = EXCLUDED.genre_age,
    model_year     = EXCLUDED.model_year,
    base_sku       = EXCLUDED.base_sku,
    is_pack        = EXCLUDED.is_pack,
    norm_txt       = EXCLUDED.norm_txt,
    computed_at    = now()
"""

_OFFER_FIELDS = (
    "id", "merchant_id", "raw_gtin", "raw_title", "raw_brand", "raw_color",
    "raw_gender", "raw_age_group", "raw_size", "raw_mpn", "raw_item_group",
    "raw_category", "deeplink",
)
_SELECT_OFFERS = f"SELECT {', '.join(_OFFER_FIELDS)} FROM raw_offer"


def compute_signatures(only_merchant: int | None = None) -> SignatureResult:
    t0 = time.time()
    write = connect()
    read = connect()
    try:
        with write.cursor() as cur:
            cur.execute(_CREATE_TEMP)

        sql = _SELECT_OFFERS
        params: tuple = ()
        if only_merchant is not None:
            sql += " WHERE merchant_id = %s"
            params = (only_merchant,)

        n = 0
        copy_sql = f"COPY _sig ({', '.join(_SIG_COLS)}) FROM STDIN"
        with read.cursor(name="ro") as src:
            src.itersize = 5_000
            src.execute(sql, params)
            with write.cursor() as cur, cur.copy(copy_sql) as cp:
                cp.set_types(
                    [
                        "bigint", "text", "bool", "text", "text[]", "text", "text",
                        "real", "text", "text", "text", "text", "int2",
                        "text", "bool", "text",
                    ]
                )
                for row in src:
                    o = dict(zip(_OFFER_FIELDS, row, strict=True))
                    cp.write_row(_signature_row(o))
                    n += 1

        with write.cursor() as cur:
            cur.execute(_UPSERT)
        write.commit()
        return SignatureResult(n, time.time() - t0)
    except Exception:
        write.rollback()
        raise
    finally:
        read.close()
        write.close()
