"""One place to open a database connection."""

from __future__ import annotations

import os

import psycopg


def connect() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (check .env)")
    return psycopg.connect(url, autocommit=False)
