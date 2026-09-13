"""Walk live product pages and count defects by class.

The catalogue measurements in `mesure_catalogue.py` read the database. This one
reads the site, which is where a defect is actually seen: a page can be perfectly
consistent in SQL and still be unreadable. Every problem found on 2026-09-13 was
found by opening a page, not by querying.

    .venv/Scripts/python.exe run_site.py          # in another window
    .venv/Scripts/python.exe ops/audit_site.py    # then this

Read-only, and it only ever talks to 127.0.0.1.
"""

from __future__ import annotations

import collections
import re
import sys
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RACINE / ".env")

from psycopg.rows import dict_row  # noqa: E402

from mcpipe.db import connect  # noqa: E402

BASE = "http://127.0.0.1:8000"
ECHANTILLON = 400

_CATEGORIE_DANS_NOM = re.compile(
    r"\b(veste|blouson|gants?|pantalon|bottes?|casque|sacoche|support)\b", re.I
)
_LIGNE = re.compile(
    r'<tr class="([^"]*)"\s+data-taille="([^"]*)"\s+data-prix="([^"]*)"\s+data-nb="(\d+)"'
)
_BOUTON = re.compile(r'data-taille="([^"]*)">([^<]*)</button>')


def _page(chemin: str) -> str:
    with urllib.request.urlopen(BASE + chemin, timeout=30) as r:  # noqa: S310
        return r.read().decode("utf-8")


def _systeme(taille: str) -> str:
    """Which notation a size is written in — mixing several on one page is a bug."""
    if re.fullmatch(r"XXS|XS|S|M|L|XL|[2-6]XL", taille):
        return "lettre"
    if re.fullmatch(r"T\d{1,2}", taille):
        return "T+chiffre"
    if re.fullmatch(r"\d{1,2}", taille):
        return "chiffre"
    if re.fullmatch(r"EU\d+", taille):
        return "EU"
    return "autre"


def echantillon() -> list[dict]:
    conn = connect()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT p.slug, p.colour_code
                   FROM product p JOIN product_stats s ON s.product_id = p.id
                   WHERE s.merchant_count >= 2
                   ORDER BY md5(p.id::text) LIMIT %s""",
                (ECHANTILLON,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def audite(pages: list[dict]) -> tuple[collections.Counter, dict[str, list[str]]]:
    compte: collections.Counter = collections.Counter()
    exemples: dict[str, list[str]] = collections.defaultdict(list)

    def note(cle: str, slug: str) -> None:
        compte[cle] += 1
        if len(exemples[cle]) < 3:
            exemples[cle].append(slug)

    for r in pages:
        slug = r["slug"]
        try:
            html = _page("/p/" + slug)
        except Exception:
            note("page en erreur", slug)
            continue

        titre = (re.search(r"<h1>([^<]*)</h1>", html) or [None, ""])[1].strip()
        tailles = [t for _v, t in _BOUTON.findall(html) if t != "Toutes"]
        lignes = _LIGNE.findall(html)

        if not titre:
            note("nom vide", slug)
        elif len(titre) < 3:
            note("nom trop court", slug)
        elif _CATEGORIE_DANS_NOM.search(titre):
            note("mot de categorie dans le nom", slug)

        if "pas de visuel" in html:
            note("aucune photo", slug)
        if "Aucune offre disponible" in html:
            note("aucune offre affichee", slug)
        if not lignes:
            note("tableau des offres vide", slug)

        if len(tailles) == 1:
            note("une seule taille proposee", slug)
        if len({_systeme(t) for t in tailles}) > 1:
            note("systemes de taille melanges", slug)

        prix = [float(p) for _c, _t, p, _n in lignes if p]
        if prix and max(prix) > 12 * min(prix):
            note("ecart de prix > x12", slug)
        if len(prix) < len(lignes):
            note("offre sans prix", slug)

        if r["colour_code"] == "unknown":
            note("produit sans couleur", slug)

    return compte, exemples


if __name__ == "__main__":
    pages = echantillon()
    compte, exemples = audite(pages)

    sortie = [f"FICHES EXAMINEES : {len(pages)}", ""]
    for cle, n in compte.most_common():
        sortie.append(f"  {cle:34} {n:>4}  ({100 * n / len(pages):5.1f} %)")
        sortie += [f"        {s[:64]}" for s in exemples[cle]]
    if not compte:
        sortie.append("  aucun defaut detecte")
    sys.stdout.buffer.write(("\n".join(sortie) + "\n").encode("utf-8", "replace"))
