"""Quelles fiches comparables n'ont pas de matière, de saison ou d'homologation ?

Écrit `couverture_caracteristique` (le pourcentage par rayon) et
`fiche_incomplete` (la liste des fiches, avec ce qui leur manque). Les deux
tables sont lues par l'écran « Caractéristiques » de l'administration.

« Manque » ne compte que ce qui a un sens pour le rayon : pas de saison pour un
casque ni une botte, pas de matière pour une pièce. Les définitions de ce qui
est « renseigné » sont CELLES DU SITE (`mcsite.queries._CARAC_SQL`), les mêmes
que celles des filtres : un pourcentage qui ne compterait pas comme le filtre
n'apprendrait rien.
"""

from __future__ import annotations

from .db import connect

# Rayons (identifiants de `category`) pour lesquels chaque caractéristique a un sens.
_CASQUES = (1, 2, 3, 4, 5)
_BLOUSONS = (6, 10)
_PANTALONS = (7,)
_GANTS = (8,)
_BOTTES = (9,)

APPLICABLE = {
    "saison": _BLOUSONS + _PANTALONS + _GANTS,
    "matiere": _CASQUES + _BLOUSONS + _PANTALONS + _GANTS + _BOTTES,
    "homologation": _CASQUES + _BLOUSONS + _PANTALONS + _GANTS + _BOTTES,
}


def _ids(t: tuple[int, ...]) -> str:
    return ", ".join(str(i) for i in t)


def recalculer() -> dict[str, int]:
    from mcsite import queries as q  # mêmes définitions que les filtres du site

    renseigne = {p: f"SELECT DISTINCT product_id FROM ({q._CARAC_SQL[p]}) x"
                 for p in ("saison", "matiere", "homologation")}
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE _liste ON COMMIT DROP AS "
                        "SELECT p.id, p.category_id, s.merchant_count "
                        "FROM product p JOIN product_stats s ON s.product_id = p.id "
                        "WHERE s.merchant_count >= 2 AND s.cheapest IS NOT NULL "
                        "AND p.status <> 'merged'")
            for p, sql in renseigne.items():
                cur.execute(f"CREATE TEMP TABLE _{p} ON COMMIT DROP AS {sql}")
            cur.execute("DELETE FROM couverture_caracteristique")
            cur.execute(f"""
                INSERT INTO couverture_caracteristique
                    (rayon, produits, saison, matiere, homologation)
                SELECT c.label_fr, count(*),
                       count(*) FILTER (WHERE l.id IN (SELECT product_id FROM _saison)),
                       count(*) FILTER (WHERE l.id IN (SELECT product_id FROM _matiere)),
                       count(*) FILTER (WHERE l.id IN (SELECT product_id FROM _homologation))
                FROM _liste l JOIN category c ON c.id = l.category_id
                GROUP BY c.label_fr""")
            cur.execute("DELETE FROM fiche_incomplete")
            cur.execute(f"""
                INSERT INTO fiche_incomplete (product_id, categorie, manque, marchands)
                SELECT l.id, l.category_id,
                       array_remove(ARRAY[
                         CASE WHEN l.category_id IN ({_ids(APPLICABLE['saison'])})
                                   AND l.id NOT IN (SELECT product_id FROM _saison)
                              THEN 'saison' END,
                         CASE WHEN l.category_id IN ({_ids(APPLICABLE['matiere'])})
                                   AND l.id NOT IN (SELECT product_id FROM _matiere)
                              THEN 'matiere' END,
                         CASE WHEN l.category_id IN ({_ids(APPLICABLE['homologation'])})
                                   AND l.id NOT IN (SELECT product_id FROM _homologation)
                              THEN 'homologation' END], NULL),
                       l.merchant_count
                FROM _liste l""")
            cur.execute("DELETE FROM fiche_incomplete WHERE cardinality(manque) = 0")
            cur.execute("SELECT count(*) FROM fiche_incomplete")
            n = cur.fetchone()[0]
        conn.commit()
        return {"fiches_incompletes": n}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
