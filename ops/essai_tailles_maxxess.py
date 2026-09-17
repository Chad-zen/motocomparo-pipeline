"""Cherche la taille PARTOUT dans le flux Maxxess / Moto-Axxe.

Écrit parce que la propriétaire trouvait suspect que trois marchands sur six ne
publient aucune taille. Vérification faite colonne par colonne, puis dans le
texte libre. Lecture seule.
"""

from __future__ import annotations

import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

MOTIF = r"taille\s*:?\s*(xs|s|m|l|xl|2xl|3xl|[0-9]{2})\M"

c = psycopg.connect(os.environ["DATABASE_URL"])

for mid, nom in ((4, "maxxess"), (5, "motoaxxe")):
    print(f"=== {nom} : la description mentionne une taille ===")
    n = c.execute(
        "select count(*) from stg_feed_row where merchant_id=%s "
        "and row->>'description' ~* %s", (mid, MOTIF)).fetchone()[0]
    print(f"  {n} ligne(s)")
    for t, d in c.execute(
        "select left(row->>'title',40), "
        "substring(row->>'description' from '(?i)(.{0,26}taille.{0,44})') "
        "from stg_feed_row where merchant_id=%s and row->>'description' ~* %s "
        "limit 8", (mid, MOTIF)):
        print(f"    {t:<40} | {(d or '').strip()[:64]}")
    print()

print("=== le titre contient-il une taille en fin de chaîne ? ===")
for mid, nom in ((4, "maxxess"), (5, "motoaxxe")):
    n = c.execute(
        "select count(*) from stg_feed_row where merchant_id=%s "
        r"and row->>'title' ~ '\s-?\s?(XS|S|M|L|XL|2XL|3XL|4XL|[3-6][0-9])$'",
        (mid,)).fetchone()[0]
    print(f"  {nom} : {n}")
