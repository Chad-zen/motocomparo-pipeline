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
import os
from dataclasses import asdict
from pathlib import Path

from ..db import connect
from . import casque

csv.field_size_limit(10 ** 7)

# Où lire le titre et la description dans chaque flux, et avec quel séparateur.
# Les quatre flux Effinity partagent un schéma de 73 colonnes ; Motoblouz et
# FC-Moto ont le leur.
_FLUX = {
    "motoblouz":   ("|", "name",  "description"),
    "fcmoto":      (",", "title", "description"),
    "speedway":    (";", "title", "description"),
    "labecanerie": (";", "title", "description"),
    "maxxess":     (";", "title", "description"),
    "motoaxxe":    (";", "title", "description"),
}

# Du plus bavard au moins bavard. La Bécanerie y figure bien qu'elle soit
# écartée de l'AFFICHAGE : ses textes restent valables, c'est son flux de PRIX
# qui est mort. Un texte figé décrit toujours correctement le produit qu'il
# décrit.
_ORDRE = ("motoblouz", "fcmoto", "speedway", "labecanerie", "maxxess", "motoaxxe")

# Les rayons qu'on sait lire, et par quel module.
_RAYONS: dict[tuple[int, ...], object] = {
    (1, 2, 3, 4, 5): casque,     # casques : parent, intégral, jet, cross, modulable
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
            for marchand, (sep, c_titre, c_desc) in _FLUX.items():
                chemin = _dossier_flux() / f"{marchand}.csv"
                if not chemin.exists():
                    continue
                with open(chemin, newline="", encoding="utf-8", errors="ignore") as f:
                    for ligne in csv.DictReader(f, delimiter=sep):
                        sku = (ligne.get("id") or ligne.get("internal reference") or "").strip()
                        pid = refs.get((marchand, sku))
                        if pid is None:
                            continue
                        textes.setdefault(pid, {})[marchand] = (
                            (ligne.get(c_titre) or "").strip(),
                            (ligne.get(c_desc) or "").strip())

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
        cur.execute("DELETE FROM product_caracteristique WHERE product_id = %s",
                    (product_id,))
        for nom, valeur in valeurs.items():
            cur.execute(
                "INSERT INTO product_caracteristique "
                "(product_id, nom, valeur, source, confiance) "
                "VALUES (%s, %s, %s, 'flux', 'lue')",
                (product_id, nom, str(valeur)))
    return len(valeurs)
