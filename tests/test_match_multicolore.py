"""La reecriture du controle « un marchand, deux couleurs, un code-barres » (18/10/2026).

`_BUILD_GTIN_UNITS` demandait, pour chaque code-barres a couleurs multiples, si UN marchand y
porte deux couleurs, en relisant toute la table `members` a chaque fois : avec Motard Bleu, 54 000
codes-barres x 640 000 lignes, plus d'une heure sans finir. Le meme controle est maintenant calcule
une fois (`codes_multicolores`) puis rejoint. Ce test prouve que les deux ecritures rendent EXACTEMENT
les memes codes-barres, sur des donnees tirees au hasard, et que le SQL du module contient bien la
nouvelle forme et plus l'ancienne.
"""

import random

import psycopg
import pytest

from mcpipe import match as m
from mcpipe.db import connect

_ANCIEN = """
SELECT c.gtin FROM (SELECT DISTINCT gtin FROM members) c
WHERE EXISTS (SELECT 1 FROM members m2
              WHERE m2.gtin = c.gtin AND m2.primary_colour IS NOT NULL
              GROUP BY m2.merchant_id HAVING count(DISTINCT m2.primary_colour) > 1)
ORDER BY 1
"""
_NOUVEAU = """
WITH codes_multicolores AS (
    SELECT DISTINCT gtin FROM (
        SELECT gtin FROM members WHERE primary_colour IS NOT NULL
        GROUP BY gtin, merchant_id HAVING count(DISTINCT primary_colour) > 1) x)
SELECT c.gtin FROM (SELECT DISTINCT gtin FROM members) c
WHERE c.gtin IN (SELECT gtin FROM codes_multicolores) ORDER BY 1
"""


def test_les_deux_ecritures_rendent_les_memes_codes_barres():
    rng = random.Random(18102026)
    couleurs = [None, "BK", "RD", "BK-RD", "WH", "BK|MAT", "GY-SI"]
    lignes = [(f"g{rng.randrange(400)}", rng.randrange(1, 8), rng.choice(couleurs))
              for _ in range(4000)]
    try:
        conn = connect()
    except Exception as exc:  # pas de base locale : le test n'a rien a verifier
        pytest.skip(f"base indisponible : {exc}")
    with conn:
        conn.execute("CREATE TEMP TABLE members (gtin text, merchant_id int, primary_colour text) ON COMMIT DROP")
        with conn.cursor().copy("COPY members FROM STDIN") as cp:
            for l in lignes:
                cp.write_row(l)
        ancien = [r[0] for r in conn.execute(_ANCIEN)]
        nouveau = [r[0] for r in conn.execute(_NOUVEAU)]
        conn.rollback()
    assert ancien == nouveau
    assert 0 < len(ancien) < 400          # le jeu d'essai exerce bien les deux branches


def test_le_module_utilise_la_forme_calculee_une_fois():
    sql = m._BUILD_GTIN_UNITS
    assert "codes_multicolores" in sql and "c.gtin IN (SELECT gtin FROM codes_multicolores)" in sql
    assert "WHERE m2.gtin = c.gtin" not in sql    # l'EXISTS correle ne doit pas revenir
