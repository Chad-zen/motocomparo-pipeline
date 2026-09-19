"""Coller la bonne fiche du revendeur sur la bonne fiche produit.

DIFFÉRENT DE SHARP, ET C'EST LE POINT CENTRAL DE CE MODULE. SHARP publie une
liste propre — « AGV / K7 » — qu'on cherche dans un titre marchand bruyant
(« Casque intégral AGV K-7 Mono Noir Mat »). Le revendeur n'a pas de liste propre :
une page par coloris, jamais de fiche « modèle seul ». Ses titres SONT aussi
bruyants que les nôtres (« HJC RPHA 12 Dravix Black-Grey-Red MC1SF »).

La comparaison ne peut donc pas être à sens unique comme avec SHARP. La seule
chose que les deux titres bruyants ont en trop, chacun de son côté, c'est la
COULEUR — et c'est la seule chose qu'on sait retirer proprement des deux, avec
le MÊME vocabulaire que le reste du pipeline
(`mcpipe.textnorm.colour_vocabulary`, déjà éprouvé sur 313 000 fiches — pas une
deuxième liste de couleurs qui dériverait de la première).

Une fois la couleur retirée des deux côtés, les deux jetons qui restent se
comparent avec l'algorithme déjà validé sur SHARP — `contient`, la garde de
prolongement, la garde d'accessoire — importé de `correspondance.py`, pas
réécrit.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..db import connect
from ..textnorm import colour_vocabulary
from .correspondance import TROP_COMMUN, contient, est_un_casque, jetons, marque

# Les rayons casque : parent, intégral, jet, cross, modulable.
CATEGORIES_CASQUE = (1, 2, 3, 4, 5)

# Ce que le revendeur publie et qu'on retient — jamais leurs notes éditoriales
# (confort, bruit : des avis, pas des faits), jamais leur texte de vente.
_NOMS = {
    "nombre_coques": "nombre_coques",
    "fermeture": "boucle",
    "matiere": "calotte",
    "poids_g": "poids_g",
    "homologation": "homologation",
}

_COULEURS = colour_vocabulary()


def _sans_couleur(texte: str) -> list[str]:
    """Les jetons d'un titre, débarrassés de la couleur et des mots vides.

    LE MÊME VOCABULAIRE QUE LE RESTE DU PIPELINE. `normalize`/`match` savent
    déjà reconnaître une couleur sur 313 000 fiches, dans six langues de
    marchand — en inventer une deuxième liste ici, c'est la garantie qu'elle
    dérive un jour de la première, en silence.
    """
    return [j for j in jetons(texte) if j not in _COULEURS and j not in TROP_COMMUN]


@dataclass
class Candidat:
    url: str
    marque: str
    jetons: list[str]         # le titre du revendeur, débarrassé de la couleur
    valeurs: dict[str, str]


def _candidats(conn) -> dict[str, list[Candidat]]:
    """marque -> fiches du revendeur, du plus long au plus court une fois la
    couleur retirée."""
    par_marque: dict[str, list[Candidat]] = {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT url, marque, modele, nombre_coques, fermeture, matiere,
                   poids_g, homologation
            FROM source_revendeur
        """)
        for url, mq, modele, coques, fermeture, matiere, poids_g, homolog in cur:
            jt = _sans_couleur(modele or "")
            if not jt or set(jt) <= TROP_COMMUN:
                continue
            valeurs = {}
            if coques is not None:
                valeurs[_NOMS["nombre_coques"]] = str(coques)
            if fermeture:
                valeurs[_NOMS["fermeture"]] = fermeture
            if matiere:
                valeurs[_NOMS["matiere"]] = matiere
            if poids_g is not None:
                valeurs[_NOMS["poids_g"]] = str(poids_g)
            if homolog:
                valeurs[_NOMS["homologation"]] = homolog
            if not valeurs:
                continue
            par_marque.setdefault(marque(mq), []).append(
                Candidat(url, mq, jt, valeurs))
    for liste in par_marque.values():
        liste.sort(key=lambda c: len(c.jetons), reverse=True)
    return par_marque


def rapprocher(trace=print) -> tuple[int, int, int, int]:
    """Écrit les caractéristiques du revendeur sur les fiches casque identifiées.

    Rend (fiches rapprochées, valeurs écrites, écartées pour ambiguïté,
    écartées parce que ce n'est pas un casque).
    Rejouable : l'écriture n'efface que ce qui vient du revendeur.
    """
    conn = connect()
    try:
        par_marque = _candidats(conn)
        if not par_marque:
            raise RuntimeError(
                "aucune fiche du revendeur en base : lancer `mcpipe revendeur` d'abord")
        trace(f"{sum(len(v) for v in par_marque.values())} fiches du revendeur, "
              f"{len(par_marque)} marques")

        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.brand_code, s.best_title
                FROM product p JOIN product_stats s ON s.product_id = p.id
                WHERE p.category_id = ANY(%s) AND p.status <> 'merged'
                  AND s.best_title IS NOT NULL
            """, (list(CATEGORIES_CASQUE),))
            fiches = cur.fetchall()

        rapprochees = valeurs_ecrites = ambigues = accessoires = 0
        with conn.cursor() as cur:
            cur.execute("DELETE FROM product_caracteristique WHERE source = 'revendeur'")
            for pid, mq, titre in fiches:
                if not est_un_casque(titre):
                    accessoires += 1
                    continue
                candidats = par_marque.get(marque(mq or ""))
                if not candidats:
                    continue

                # LE SENS S'INVERSE PAR RAPPORT À SHARP. Là-bas, un modèle
                # SHARP propre était cherché dans un titre bruyant. Ici, les
                # deux titres sont bruyants : on compare le PLUS COURT des
                # deux jeu de jetons (une fois la couleur retirée) contre le
                # plus long, avec la même garde de prolongement — elle
                # fonctionne dans les deux sens, elle ne fait que refuser un
                # jeton de trop après la correspondance.
                notre_titre = _sans_couleur(titre)
                if not notre_titre or set(notre_titre) <= TROP_COMMUN:
                    continue

                trouves = []
                for c in candidats:
                    court, long_ = ((notre_titre, c.jetons)
                                    if len(notre_titre) <= len(c.jetons)
                                    else (c.jetons, notre_titre))
                    if court and contient(long_, court):
                        trouves.append(c)
                if not trouves:
                    continue

                # PAS `correspondance.choisir()` ICI : il recalcule les jetons
                # du TITRE COMPLET (couleur incluse) pour les comparer aux
                # candidats — exactement ce qu'on vient d'éviter. La même
                # règle s'applique à la main : le plus long jeu de jetons
                # gagne, une égalité ne tranche rien.
                plus_long = max(len(c.jetons) for c in trouves)
                a_egalite = [c for c in trouves if len(c.jetons) == plus_long]
                if len(a_egalite) != 1:
                    ambigues += 1
                    continue
                choisi = a_egalite[0]

                for nom, valeur in choisi.valeurs.items():
                    cur.execute("""
                        INSERT INTO product_caracteristique
                            (product_id, nom, valeur, source, confiance)
                        VALUES (%s, %s, %s, 'revendeur', 'annoncee')
                        ON CONFLICT (product_id, nom, source) DO UPDATE SET
                            valeur = EXCLUDED.valeur, calcule_le = now()
                    """, (pid, nom, valeur))
                    valeurs_ecrites += 1
                rapprochees += 1
        conn.commit()
        return rapprochees, valeurs_ecrites, ambigues, accessoires
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
