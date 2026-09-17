"""Sort un extrait lisible des flux Maxxess et Moto-Axxe, pour vérification.

Les flux bruts font 73 colonnes, dont une soixantaine vides ou sans intérêt
(pneus, dimensions de colis, dates de promotion). Ce script en tire les douze
qui décident du rapprochement, et écrit à côté un résumé chiffré : combien de
lignes, quelles colonnes sont remplies, et la question qui nous occupe — la
taille est-elle renseignée quelque part.

    python ops/extrait_maxxess_motoaxxe.py

Écrit dans `ops/verif/`. Lecture seule sur les flux.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
FLUX = RACINE / "feeds"
SORTIE = RACINE / "ops" / "verif"
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Les colonnes qui décident quelque chose. `size`, `size_system` et `size_type`
# sont là précisément pour qu'on puisse constater qu'elles sont vides.
GARDEES = ["id", "mpn", "gtin", "brand", "title", "color", "size", "size_system",
           "size_type", "item_group_id", "price", "availability", "category",
           "category_level2", "link"]


def extraire(code: str) -> None:
    src = FLUX / f"{code}.csv"
    if not src.exists():
        print(f"  {code}: fichier absent ({src})")
        return

    SORTIE.mkdir(parents=True, exist_ok=True)
    dest = SORTIE / f"{code}-extrait.csv"
    remplies: Counter[str] = Counter()
    lignes = 0
    pages: Counter[str] = Counter()

    with src.open(encoding="utf-8-sig", newline="") as fh:
        lecteur = csv.DictReader(fh, delimiter=";")
        colonnes = lecteur.fieldnames or []
        with dest.open("w", encoding="utf-8-sig", newline="") as out:
            ecrivain = csv.DictWriter(
                out, fieldnames=[c for c in GARDEES if c in colonnes],
                delimiter=";", extrasaction="ignore")
            ecrivain.writeheader()
            for ligne in lecteur:
                lignes += 1
                for k, v in ligne.items():
                    if (v or "").strip():
                        remplies[k] += 1
                # la page produit, derrière le lien d'affiliation
                lien = ligne.get("link") or ""
                cible = lien.split("url=")[-1] if "url=" in lien else lien
                pages[cible.split("%3F")[0].split("?")[0]] += 1
                ecrivain.writerow(ligne)

    print(f"\n=== {code} ===")
    print(f"  {lignes} lignes, {len(colonnes)} colonnes")
    print(f"  extrait -> {dest.name}")
    print(f"  pages produit distinctes : {len(pages)}")
    plusieurs = sum(1 for n in pages.values() if n > 1)
    print(f"  pages portant PLUSIEURS lignes : {plusieurs}"
          f"   <- si 0, une ligne = un produit, jamais une taille")
    print("  la taille :")
    for col in ("size", "size_system", "size_type", "item_group_id"):
        if col in colonnes:
            print(f"    {col:<15} rempli sur {remplies[col]:>6} / {lignes}")
    print("  colonnes vides sur TOUTES les lignes :")
    vides = [c for c in colonnes if remplies[c] == 0]
    print("    " + (", ".join(vides) if vides else "aucune"))


if __name__ == "__main__":
    for code in ("maxxess", "motoaxxe"):
        extraire(code)
    print(f"\nExtraits écrits dans {SORTIE}")
