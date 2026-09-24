"""Les caractéristiques lues dans les descriptions des flux marchands.

LE PROBLÈME QU'IL A FALLU TRANCHER D'ABORD. `raw_offer` ne porte PAS les
descriptions : le pipeline ne les a jamais ingérées. Elles n'existent que dans
les fichiers de flux, sur le disque.

Deux voies, et on a mesuré avant de choisir :

  * les INGÉRER — environ 400 Mo de prose pour tout le catalogue, dont 324 Mo
    pour le seul Motoblouz (308 853 offres à 1 049 signes de médiane). Il
    faudrait toucher `load` et `normalize`, c'est-à-dire l'étape la plus
    risquée du pipeline, pour stocker un texte qu'on lit une fois et dont on
    ne garde que neuf valeurs.

  * LIRE LES FICHIERS au moment du calcul. Ils sont déjà là, retéléchargés
    chaque nuit. On n'écrit que le résultat.

La seconde gagne, et le compromis est assumé : le calcul n'est possible que
tant que le fichier du jour est sur le disque. Si on devait un jour recalculer
sans retélécharger, il faudrait la première. C'est écrit ici pour que ce soit
une décision, et non une surprise.

L'ORDRE DE PRIORITÉ ENTRE MARCHANDS est celui de la richesse mesurée, pas une
préférence commerciale : sur un casque, Motoblouz écrit 1 049 signes de
médiane, FC-Moto 157, La Bécanerie 127. Le premier qui sait répond.
"""

from __future__ import annotations

import csv
import html
import os
from dataclasses import asdict
from pathlib import Path

from ..db import connect
from ..feeds import FEEDS, FeedSpec
from ..normalize import _ci_get, _merchant_sku
from . import blouson, botte, casque, gant, pantalon

csv.field_size_limit(10 ** 7)

# LA CLÉ DE JOINTURE EST CELLE DU PIPELINE, PAS UNE DEUXIÈME ÉCRITE ICI.
#
# Ce module a d'abord cherché la référence marchande dans la colonne `id`, en
# repli sur `internal reference`. C'était juste pour quatre marchands sur six et
# faux pour les deux autres, en silence :
#
#   * FC-MOTO. Sa référence est `mpn`, en repli sur `gtin` puis `id` — la
#     colonne `id` du flux est un hachage dont la stabilité n'est pas établie,
#     et `normalize` ne s'en sert pas. Sur les blousons, 27 330 offres liées et
#     UNE SEULE description retrouvée. Le marchand le mieux rempli du catalogue
#     (couleur 90 %, taille 94 %, mpn 99 %) était absent des caractéristiques.
#
#   * MAXXESS ET MOTO-AXXE. Leurs identifiants de flux changent à chaque
#     rafraîchissement, donc `normalize` fabrique la sienne à partir de l'URL
#     cible : `u:<md5>`. Aucune valeur de la colonne `id` ne peut y correspondre.
#     Zéro description retrouvée pour les deux.
#
# Rien ne le signalait : les fiches trouvées étaient correctement renseignées,
# et les manquantes ressemblaient à des descriptions vides. On lit donc la
# référence avec `_merchant_sku`, LA MÊME FONCTION qui l'a écrite en base. Deux
# façons de calculer une clé de jointure finissent toujours par diverger ; il
# n'y en a plus qu'une.


# LES ENTITÉS HTML SE DÉCODENT ICI, UNE FOIS, POUR TOUT LE MONDE.
#
# 17,7 % des descriptions Motoblouz portent des entités non décodées —
# `&nbsp;`, `&amp;`, `&eacute;` — mesuré le 2026-09-24 sur 120 001 lignes. Ce
# n'est pas un détail d'affichage : les extracteurs découpent le texte sur la
# ponctuation, et le point-virgule de `&nbsp;` y crée une FRONTIÈRE DE SEGMENT
# FANTÔME, au milieu d'une phrase que le marchand n'a jamais coupée.
#
# Le défaut a été trouvé par son symptôme le plus absurde : le blouson Furygan
# Mistral Evo 3 et sa version dame, même vêtement et description jumelle,
# ressortaient l'un avec « protections coudes fournies » et l'autre avec
# « préparé ». La version homme écrivait « Protections épaules&nbsp;D3O », la
# version dame « Protections épaules D3O ». Le `;` de l'entité coupait la
# phrase juste avant « Prédisposé à recevoir une protection dorsale », et
# sauvait la lecture PAR ACCIDENT. Une réponse juste pour une mauvaise raison
# est une réponse qui se trompera ailleurs.
#
# Décoder au bon endroit — le lecteur de flux — plutôt que dans chacun des
# cinq rayons : deux façons de nettoyer un texte finissent toujours par
# diverger, comme les deux clés de jointure au-dessus.
def _lignes(feed: FeedSpec, chemin: Path):
    """(référence marchande, titre, description) pour chaque ligne du flux."""
    cols = feed.columns
    with open(chemin, newline="", encoding="utf-8", errors="ignore") as f:
        for ligne in csv.DictReader(f, delimiter=feed.delimiter):
            deeplink = _ci_get(ligne, cols.get("link", []))
            if not deeplink:
                continue
            sku = _merchant_sku(feed, ligne, deeplink)
            if not sku:
                continue
            yield (sku,
                   html.unescape(_ci_get(ligne, cols.get("title", [])) or "").strip(),
                   html.unescape(_ci_get(ligne, cols.get("description", [])) or "").strip())


# Du plus bavard au moins bavard. La Bécanerie y figure bien qu'elle soit
# écartée de l'AFFICHAGE : ses textes restent valables, c'est son flux de PRIX
# qui est mort. Un texte figé décrit toujours correctement le produit qu'il
# décrit.
_ORDRE = ("motoblouz", "fcmoto", "speedway", "labecanerie", "maxxess", "motoaxxe")

# Les rayons qu'on sait lire, et par quel module.
_RAYONS: dict[tuple[int, ...], object] = {
    (1, 2, 3, 4, 5): casque,     # casques : parent, intégral, jet, cross, modulable
    (6, 10): blouson,            # blousons, vestes, et combinaisons
    (8,): gant,                  # gants
    (7,): pantalon,              # pantalons et jeans
    (9,): botte,                 # bottes et chaussures
}


def _dossier_flux() -> Path:
    return Path(os.environ.get("FEEDS_DIR", "feeds"))


def _references(conn, cats: tuple[int, ...]) -> dict[tuple[str, str], int]:
    """(code marchand, référence marchande) -> fiche.

    Chargé en mémoire : 767 000 entrées tiennent dans quelques dizaines de Mo,
    et l'alternative — une requête par ligne de flux — ferait des centaines de
    milliers d'allers-retours.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT m.code, o.merchant_sku, o.product_id
            FROM raw_offer o
            JOIN merchant m ON m.id = o.merchant_id
            JOIN product p ON p.id = o.product_id
            WHERE o.linked_status = 'linked' AND o.is_live
              AND p.category_id = ANY(%s) AND p.status <> 'merged'
        """, (list(cats),))
        return {(c, s): pid for c, s, pid in cur}


def calculer(rayon: str = "casque") -> tuple[int, int]:
    """Relit les descriptions du jour et réécrit les caractéristiques.

    Rend (fiches renseignées, caractéristiques écrites). Rejouable : chaque
    fiche est recalculée ENTIÈREMENT, jamais complétée — sans quoi une valeur
    retirée d'une description resterait en base pour toujours, et personne ne
    le verrait.
    """
    conn = connect()
    try:
        total_fiches = total_lignes = 0
        for cats, module in _RAYONS.items():
            refs = _references(conn, cats)
            if not refs:
                continue
            # fiche -> {marchand: (titre, description)}
            textes: dict[int, dict[str, tuple[str, str]]] = {}
            for marchand, feed in FEEDS.items():
                chemin = _dossier_flux() / f"{marchand}.csv"
                if not chemin.exists():
                    continue
                for sku, titre, desc in _lignes(feed, chemin):
                    pid = refs.get((marchand, sku))
                    if pid is not None:
                        textes.setdefault(pid, {})[marchand] = (titre, desc)

            for pid, par_marchand in textes.items():
                lus = [module.lire(*par_marchand[m]) for m in _ORDRE if m in par_marchand]
                n = _ecrire(conn, pid, module.fusionner(lus))
                if n:
                    total_fiches += 1
                total_lignes += n
        conn.commit()
        return total_fiches, total_lignes
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ecrire(conn, product_id: int, lu) -> int:
    valeurs = {k: v for k, v in asdict(lu).items()
               if v is not None and k != "sources"}
    with conn.cursor() as cur:
        # On efface AVANT d'écrire : une caractéristique qui disparaît d'une
        # description doit disparaître de la fiche.
        #
        # MAIS SEULEMENT CE QUI VIENT DES FLUX. Un effacement sans condition
        # emportait aussi les valeurs des sources extérieures — la note de
        # sécurité SHARP et le poids pesé auraient disparu toutes les nuits à
        # 04:04, pour revenir au prochain relevé mensuel. Une donnée qui va et
        # vient sans raison est pire qu'une donnée absente.
        cur.execute("DELETE FROM product_caracteristique "
                    "WHERE product_id = %s AND source = 'flux'",
                    (product_id,))
        for nom, valeur in valeurs.items():
            # ET UNE PHRASE DE VENTE NE RECOUVRE PAS UNE MESURE. Les deux
            # sources se rencontrent sur les mêmes noms — la calotte, le poids.
            # Quand un laboratoire a pesé, ce qu'écrit le vendeur ne compte
            # plus : `DO NOTHING` laisse la valeur mesurée en place.
            cur.execute(
                "INSERT INTO product_caracteristique "
                "(product_id, nom, valeur, source, confiance) "
                "VALUES (%s, %s, %s, 'flux', 'lue') "
                "ON CONFLICT (product_id, nom, source) DO UPDATE SET "
                "valeur = EXCLUDED.valeur, calcule_le = now()",
                (product_id, nom, str(valeur)))
    return len(valeurs)
