"""Tirer au sort des descriptions marchandes d'un rayon, pour LIRE avant d'ecrire.

Un extracteur ne se concoit pas de memoire : les marchands ont leur vocabulaire,
et c'est lui qu'il faut voir. Cet outil sort des descriptions reelles, avec la
fiche et le marchand d'ou elles viennent, pour qu'on puisse revenir a la source
quand une extraction est contestee.

    python outils/echantillon.py --cat 6 -n 25
    python outils/echantillon.py --cat 8 -n 15 --motif "membrane|gore.?tex"
    python outils/echantillon.py --cat 6 --stats

`--motif` est la deuxieme moitie du travail : une fois l'extracteur ecrit, on
relit les descriptions OU IL A TROUVE QUELQUE CHOSE, avec le contexte autour du
mot. C'est comme ca que les quatre pieges du rayon casque sont apparus, et
aucun d'eux ne se voyait dans un taux de couverture.
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
csv.field_size_limit(10 ** 7)

from dotenv import load_dotenv  # noqa: E402

load_dotenv()  # comme la CLI : .env avant que quoi que ce soit ne lise l'environnement

from mcpipe.caracteristiques import _lignes, _ORDRE, _dossier_flux  # noqa: E402
from mcpipe.feeds import FEEDS  # noqa: E402
from mcpipe.db import connect  # noqa: E402


def descriptions(cats: list[int]) -> dict[int, dict[str, tuple[str, str]]]:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT m.code, o.merchant_sku, o.product_id
                FROM raw_offer o
                JOIN merchant m ON m.id = o.merchant_id
                JOIN product p ON p.id = o.product_id
                WHERE o.linked_status = 'linked' AND o.is_live
                  AND p.category_id = ANY(%s) AND p.status <> 'merged'
            """, (cats,))
            refs = {(c, s): pid for c, s, pid in cur}
    finally:
        conn.close()

    textes: dict[int, dict[str, tuple[str, str]]] = {}
    for marchand, feed in FEEDS.items():
        chemin = _dossier_flux() / f"{marchand}.csv"
        if not chemin.exists():
            continue
        for sku, titre, desc in _lignes(feed, chemin):
            pid = refs.get((marchand, sku))
            if pid is not None:
                textes.setdefault(pid, {})[marchand] = (titre, desc)
    return textes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", required=True,
                    help="ids de categorie, separes par des virgules")
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--motif", help="ne garder que les textes qui matchent, "
                                    "et surligner le contexte autour")
    ap.add_argument("--contexte", type=int, default=120)
    ap.add_argument("--stats", action="store_true",
                    help="longueur des descriptions par marchand, sans les sortir")
    ap.add_argument("--graine", type=int, default=0)
    a = ap.parse_args()

    cats = [int(x) for x in a.cat.split(",")]
    textes = descriptions(cats)
    print(f"# {len(textes)} fiches avec au moins une description "
          f"(categories {cats})\n", file=sys.stderr)

    if a.stats:
        par_marchand: dict[str, list[int]] = {}
        for par in textes.values():
            for m, (_, d) in par.items():
                par_marchand.setdefault(m, []).append(len(d))
        for m in _ORDRE:
            L = sorted(par_marchand.get(m, []))
            if not L:
                continue
            print(f"{m:<14} {len(L):>7} fiches   mediane {L[len(L)//2]:>6} signes"
                  f"   vides {sum(1 for x in L if x == 0):>6}")
        return 0

    rx = re.compile(a.motif, re.I) if a.motif else None
    ids = sorted(textes)
    random.Random(a.graine).shuffle(ids)

    sortis = 0
    for pid in ids:
        if sortis >= a.n:
            break
        for marchand in _ORDRE:
            if marchand not in textes[pid]:
                continue
            titre, desc = textes[pid][marchand]
            if rx and not rx.search(desc):
                continue
            print(f"\n{'=' * 78}\n# fiche {pid} — {marchand}\n{titre}\n{'-' * 78}")
            if rx:
                # Le contexte, pas le debut du texte : c'est la phrase AUTOUR du
                # mot detecte qui dit si la detection est juste.
                for m in rx.finditer(desc):
                    d, f = max(0, m.start() - a.contexte), m.end() + a.contexte
                    print(f"…{desc[d:f]}…\n")
            else:
                print(desc[:1500])
            sortis += 1
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
