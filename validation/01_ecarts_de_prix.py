"""Controle 1 — une fiche ne doit pas regrouper des offres a des prix sans rapport.

LE PROBLEME QU'ON CHERCHE (vu le 19/10/2026) : sur la fiche « Voca Racing leviers »,
trois offres a 4 a 9 EUR et une a 44 EUR. Ce n'etait pas le meme article : la
mousse de levier et la protection en aluminium portaient le meme titre chez un
marchand. Un comparateur qui affiche ca ment a ses visiteurs.

LA METHODE, en trois temps :
  1. SQL : on ramene une ligne par offre vivante (id de fiche, prix). C'est tout.
  2. pandas : on regroupe par fiche et on compare le plus bas au plus haut prix.
  3. SQL de nouveau, mais seulement pour les fiches suspectes : on va chercher les
     titres et les marchands pour pouvoir juger a l'oeil.

POURQUOI NE PAS TOUT FAIRE EN SQL ? On pourrait (un GROUP BY ... HAVING suffit).
Ici on utilise pandas expres : c'est l'outil qu'on utilise pour EXPLORER, changer un
seuil, trier, tracer — sans relancer une requete de plusieurs secondes a chaque essai.

COMMENT LE LANCER (depuis la racine du projet, base locale = copie de la production) :
    .venv/Scripts/python.exe validation/01_ecarts_de_prix.py
    .venv/Scripts/python.exe validation/01_ecarts_de_prix.py --seuil 3

EXERCICES (pour que ce soit a toi) :
  A. Mets le seuil a 3, puis a 10. Combien de fiches changent ? Lesquelles disparaissent ?
  B. Remplace « plus haut / plus bas » par « chaque offre contre la MEDIANE des autres
     offres de la fiche ». Pourquoi est-ce plus robuste quand une fiche a 20 offres
     et une seule aberrante ?
  C. Ajoute le marchand de l'offre la plus chere. Y en a-t-il un qui revient souvent ?
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# permet de lancer le script depuis la racine sans installer le paquet
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mcpipe.db import connect  # noqa: E402

# Temps 1 : une ligne par offre vivante. On ne ramene que ce dont pandas a besoin
# (deux colonnes) : 900 000 lignes de deux nombres, c'est leger ; avec les titres,
# ce serait dix fois plus lourd pour rien.
REQUETE_PRIX = """
    SELECT o.product_id, o.price
    FROM raw_offer o
    JOIN product p ON p.id = o.product_id
    WHERE o.is_live AND o.price > 0 AND p.status <> 'merged'
"""

# Temps 3 : le detail, seulement pour les fiches suspectes (`ANY(%s)` = « dans cette liste »).
REQUETE_DETAIL = """
    SELECT o.product_id, p.slug, m.code AS marchand, o.price, left(o.raw_title, 60) AS titre
    FROM raw_offer o
    JOIN product p ON p.id = o.product_id
    JOIN merchant m ON m.id = o.merchant_id
    WHERE o.is_live AND o.price > 0 AND o.product_id = ANY(%s)
    ORDER BY o.product_id, o.price
"""


def ecarts_de_prix(offres: pd.DataFrame, seuil: float = 5.0) -> pd.DataFrame:
    """Les fiches dont le prix le plus haut vaut au moins `seuil` fois le plus bas.

    `offres` : un DataFrame avec les colonnes `product_id` et `price`.
    Rend une ligne par fiche suspecte : nombre d'offres, prix mini, prix maxi, rapport.
    Fonction PURE (aucune base) : c'est ce qui permet de la tester avec trois lignes.
    """
    # groupby : « regroupe les lignes par fiche » ; agg : « et calcule ces resumes ».
    par_fiche = offres.groupby("product_id")["price"].agg(
        nb_offres="count", prix_min="min", prix_max="max")
    # une fiche d'une seule offre n'a rien a comparer
    par_fiche = par_fiche[par_fiche["nb_offres"] > 1].copy()
    par_fiche["rapport"] = par_fiche["prix_max"] / par_fiche["prix_min"]
    suspectes = par_fiche[par_fiche["rapport"] >= seuil]
    return suspectes.sort_values("rapport", ascending=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seuil", type=float, default=5.0, help="rapport prix max / prix min (defaut 5)")
    args = ap.parse_args()

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(REQUETE_PRIX)
            # les prix reviennent en Decimal : on les passe en nombres a virgule pour pandas
            offres = pd.DataFrame(cur.fetchall(), columns=["product_id", "price"]).astype(
                {"price": "float64"})
            print(f"{len(offres):,} offres vivantes lues, "
                  f"{offres['product_id'].nunique():,} fiches".replace(",", " "))

            suspectes = ecarts_de_prix(offres, args.seuil)
            print(f"{len(suspectes)} fiches avec un ecart d'au moins {args.seuil:g}x")

            if suspectes.empty:
                return
            cur.execute(REQUETE_DETAIL, (list(suspectes.index),))
            detail = pd.DataFrame(cur.fetchall(), columns=[
                "product_id", "slug", "marchand", "price", "titre"]).astype({"price": "float64"})
    finally:
        conn.close()

    # on rattache le rapport a chaque ligne de detail, pour trier et lire facilement
    detail = detail.merge(suspectes[["rapport"]], left_on="product_id", right_index=True)
    detail = detail.sort_values(["rapport", "product_id", "price"], ascending=[False, True, True])

    sortie = Path(__file__).parent / "sorties" / f"01_ecarts_de_prix_seuil{args.seuil:g}.csv"
    detail.to_csv(sortie, index=False, sep=";", encoding="utf-8-sig")
    print(f"detail ecrit dans {sortie}")
    print("\nles 5 fiches les plus ecartees :")
    for pid, groupe in list(detail.groupby("product_id", sort=False))[:5]:
        r = groupe["rapport"].iloc[0]
        print(f"\n  {groupe['slug'].iloc[0]}  (rapport {r:.1f}x)")
        for _, o in groupe.iterrows():
            print(f"    {o['price']:>9.2f} EUR  {o['marchand']:<12s} {o['titre']}")


if __name__ == "__main__":
    main()
