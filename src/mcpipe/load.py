"""Stage 2 — load a downloaded feed CSV into the `stg_feed_row` staging table.

One CSV line -> one JSONB row. The whole feed row is kept verbatim; `normalize`
is what decides which fields matter. Uses Postgres COPY (streamed from the
client) so ~300k rows land in a few seconds.

Every load opens a `feed_run` row so we always know when each merchant was last
ingested and how many rows came in.
"""

from __future__ import annotations

import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from .db import connect
from .feeds import FEEDS, FeedSpec

# feed rows have long description fields; lift Python's CSV field cap
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


@dataclass
class LoadResult:
    feed: str
    rows: int
    seconds: float
    feed_run_id: int


def _ensure_merchants(conn: psycopg.Connection) -> None:
    """Keep the `merchant` table in sync with feeds.py (the single source)."""
    with conn.cursor() as cur:
        for f in FEEDS.values():
            cur.execute(
                """
                INSERT INTO merchant (id, code, platform, gtin_trust, reliability_rank)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    code = EXCLUDED.code,
                    platform = EXCLUDED.platform,
                    gtin_trust = EXCLUDED.gtin_trust,
                    reliability_rank = EXCLUDED.reliability_rank
                """,
                (f.merchant_id, f.code, f.platform, f.gtin_trust, f.reliability_rank),
            )
    conn.commit()


def load_feed(feed: FeedSpec, csv_path: Path) -> LoadResult:
    if not csv_path.exists():
        raise FileNotFoundError(f"{csv_path} — run `mcpipe fetch` first")

    t0 = time.time()
    conn = connect()
    try:
        _ensure_merchants(conn)

        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO feed_run (merchant_id, status) VALUES (%s, 'running') RETURNING id",
                (feed.merchant_id,),
            )
            run_id = cur.fetchone()[0]
            cur.execute("DELETE FROM stg_feed_row WHERE merchant_id = %s", (feed.merchant_id,))

        n = 0
        copy_sql = "COPY stg_feed_row (feed_run_id, merchant_id, row) FROM STDIN"
        with (
            conn.cursor() as cur,
            cur.copy(copy_sql) as cp,
            csv_path.open("r", encoding="utf-8", errors="replace", newline="") as fh,
        ):
            cp.set_types(["bigint", "smallint", "jsonb"])
            reader = csv.reader(fh, delimiter=feed.delimiter, quotechar='"')
            header = [h.strip() for h in next(reader)]
            for rec in reader:
                if not rec:
                    continue
                obj = dict(zip(header, rec, strict=False))
                cp.write_row((run_id, feed.merchant_id, Jsonb(obj)))
                n += 1

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE feed_run SET status = 'ok', finished_at = now(), row_count = %s"
                " WHERE id = %s",
                (n, run_id),
            )
        conn.commit()
        return LoadResult(feed.code, n, time.time() - t0, run_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
