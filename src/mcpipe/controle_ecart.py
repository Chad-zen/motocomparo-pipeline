"""Controle nocturne : les fiches dont deux marchands sont a plus de 50 % d'ecart.

Demande de la proprietaire (22/10/2026), apres la fiche Airoh ST : un pinlock (insert
anti-buee, 34,90 EUR) rattache a la visiere (54,95 EUR), ecart de 57 %. Les gardes de
`match` (3x sans code-barres, 5x avec) ne le voyaient pas.

Ce controle NE SEPARE RIEN. Mesure le 22/10/2026 sur 71 882 fiches comparees : 5 990 sont
a plus de 50 % (1 017 a 2x, 173 a 3x). Beaucoup sont de vraies soldes ; les couper toutes
detruirait des comparaisons justes. Il les ECRIT dans `controle_ecart`, classees par
niveau, pour qu'une personne tranche, et se souvient des fiches jugees legitimes
(`statut = 'ok'`) pour ne pas les resortir chaque nuit.

Niveaux :
  * fort  : un meme marchand porte deux codes-barres dont les titres different par autre
            chose qu'une taille (deux articles), OU l'ecart depasse 2x ;
  * moyen : plusieurs codes-barres sur la fiche, ecart entre 1,5x et 2x ;
  * faible: un seul code-barres : un prix different pour le meme article, donc une promo ou
            une erreur de prix, pas un rapprochement a tort.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import textnorm as tn
from .db import connect

SEUIL = 1.5

_SQL = """
WITH o AS (
    SELECT o.product_id, o.id AS offre_id, o.merchant_id, m.code AS marchand,
           o.price, o.gtin, o.raw_title
    FROM raw_offer o
    JOIN merchant m ON m.id = o.merchant_id AND m.affiche
    JOIN product p ON p.id = o.product_id AND p.status <> 'merged'
    WHERE o.linked_status = 'linked' AND o.is_live AND o.price > 0
),
g AS (
    SELECT product_id, count(DISTINCT merchant_id) AS nb_marchands,
           count(DISTINCT gtin) AS nb_gtin, min(price) AS bas, max(price) AS haut
    FROM o GROUP BY product_id
    HAVING count(DISTINCT merchant_id) >= 2 AND max(price) >= %(seuil)s * min(price)
),
mm AS (
    -- un marchand qui porte plusieurs codes-barres sur la fiche : ses titres, pour juger en
    -- Python si ce sont des TAILLES (rien d'anormal) ou deux articles (pinlock et visiere)
    SELECT o.product_id, o.merchant_id, array_agg(DISTINCT o.raw_title) AS titres
    FROM o JOIN g USING (product_id)
    GROUP BY o.product_id, o.merchant_id HAVING count(DISTINCT o.gtin) > 1
),
mm2 AS (
    SELECT product_id, json_agg(to_json(titres)) AS titres FROM mm GROUP BY product_id
),
bas AS (
    SELECT DISTINCT ON (o.product_id) o.product_id, o.marchand, o.raw_title
    FROM o JOIN g USING (product_id) ORDER BY o.product_id, o.price, o.offre_id
),
haut AS (
    SELECT DISTINCT ON (o.product_id) o.product_id, o.marchand, o.raw_title
    FROM o JOIN g USING (product_id) ORDER BY o.product_id, o.price DESC, o.offre_id
)
SELECT g.product_id, g.nb_marchands, g.nb_gtin, g.bas, g.haut,
       bas.marchand, bas.raw_title, haut.marchand, haut.raw_title,
       mm2.titres AS titres_par_marchand
FROM g JOIN bas USING (product_id) JOIN haut USING (product_id)
LEFT JOIN mm2 USING (product_id)
"""


@dataclass
class Resultat:
    fiches: int = 0
    nouvelles: int = 0
    resolues: int = 0
    par_niveau: dict[str, int] | None = None


def mots_qui_different(a: str | None, b: str | None) -> str:
    """Les mots d'un titre absents de l'autre : « pinlock » entre « Airoh ST Pinlock
    Visiere » et « Airoh ST Visiere ». Ce que la personne qui relit doit voir en premier."""
    ta = set(tn.norm_txt(a).split()) if a else set()
    tb = set(tn.norm_txt(b).split()) if b else set()
    vus = sorted(w for w in (ta ^ tb) if len(w) > 2)
    return " ".join(vus[:8])


_TAILLE = re.compile(r"^(?:[0-9]+(?:[/.,-][0-9]+)?|x{0,3}[sl]|xx?l|[2-6]xl|xs|taille|t[0-9]+)$")


def deux_articles_chez_un_marchand(titres_par_marchand) -> bool:
    """Un meme marchand porte deux codes-barres sur la fiche : des TAILLES (les titres ne
    different que par un nombre ou S/M/L) ou deux ARTICLES (un mot en plus : « pinlock »).
    Les tailles sont le cas courant ; seul le second est suspect."""
    for titres in titres_par_marchand or []:
        mots = [set(tn.norm_txt(x).split()) for x in titres if x]
        for i, a in enumerate(mots):
            for b in mots[i + 1:]:
                if any(not _TAILLE.match(w) and len(w) > 2 for w in a ^ b):
                    return True
    return False


def niveau(ratio: float, nb_gtin: int, meme_marchand_2_gtin: bool) -> str:
    if meme_marchand_2_gtin or ratio >= 2:
        return "fort"
    if nb_gtin > 1:
        return "moyen"
    return "faible"


def controler(seuil: float = SEUIL) -> Resultat:
    res = Resultat(par_niveau={"fort": 0, "moyen": 0, "faible": 0})
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_SQL, {"seuil": seuil})
            lignes = cur.fetchall()
            vus: list[int] = []
            for (pid, nm, ng, bas, haut, m_bas, t_bas, m_haut, t_haut, titres_mm) in lignes:
                ratio = round(float(haut) / float(bas), 2)
                mm2 = deux_articles_chez_un_marchand(titres_mm)
                niv = niveau(ratio, ng, mm2)
                res.par_niveau[niv] += 1
                vus.append(pid)
                cur.execute(
                    """
                    INSERT INTO controle_ecart (product_id, ratio, prix_bas, prix_haut, marchand_bas,
                        marchand_haut, titre_bas, titre_haut, nb_marchands, nb_gtin,
                        meme_marchand_2_gtin, mots, niveau)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (product_id) DO UPDATE SET
                        ratio = EXCLUDED.ratio, prix_bas = EXCLUDED.prix_bas,
                        prix_haut = EXCLUDED.prix_haut, marchand_bas = EXCLUDED.marchand_bas,
                        marchand_haut = EXCLUDED.marchand_haut, titre_bas = EXCLUDED.titre_bas,
                        titre_haut = EXCLUDED.titre_haut, nb_marchands = EXCLUDED.nb_marchands,
                        nb_gtin = EXCLUDED.nb_gtin,
                        meme_marchand_2_gtin = EXCLUDED.meme_marchand_2_gtin,
                        mots = EXCLUDED.mots, niveau = EXCLUDED.niveau, vu_le = current_date
                    RETURNING (xmax = 0)
                    """,
                    (pid, ratio, bas, haut, m_bas, m_haut, t_bas, t_haut, nm, ng, mm2,
                     mots_qui_different(t_bas, t_haut), niv),
                )
                if cur.fetchone()[0]:
                    res.nouvelles += 1
            res.fiches = len(lignes)
            # une fiche qui n'est plus a l'ecart (corrigee, ou prix revenu) sort de la liste a
            # revoir ; une fiche jugee « ok » reste memorisee
            cur.execute(
                "DELETE FROM controle_ecart WHERE statut = 'a_revoir' AND NOT (product_id = ANY(%s))",
                (vus,),
            )
            res.resolues = cur.rowcount
        conn.commit()
        return res
    finally:
        conn.close()
