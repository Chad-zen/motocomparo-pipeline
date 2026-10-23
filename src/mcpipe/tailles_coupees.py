"""Un meme casque, deux fiches : les tailles coupees en deux (23/10/2026).

LE CAS. Le Shoei J-Cruise 3 bleu mat existait en deux fiches : XS et S sur l'une, M et L sur
l'autre. Les codes-barres se suivent (…700, …717, …724, …731) et La Becanerie nomme les tailles
« blue metallic mat » partout. Aucune regle existante ne les rapprochait : `consolider` part des
codes-barres eclates, et ici chaque code-barres n'est que sur une seule fiche. Mesure du
23/10 : 309 paires de casques dans ce cas, toutes fusionnees a la main ce jour-la.

LA REGLE (validee par la proprietaire sur un echantillon). Deux fiches de casque sont la meme si :
  - un marchand qui met la COULEUR dans son titre (La Becanerie, Speedway) donne exactement le
    meme titre, taille retiree, aux deux ;
  - elles portent le meme nom de modele ;
  - leurs prix mini sont a moins de 30 % l'un de l'autre ;
  - chacune a des tailles connues et les deux jeux de tailles ne se recoupent PAS.
Les paires qui se chevauchent (trois fiches pour un casque) sont laissees : on ne devine pas.
Motoblouz et FC-Moto sont exclus : leur titre est le meme pour toutes les couleurs.

Ce module ne fusionne pas lui-meme : il inscrit les paires comme `validee` dans
`fusion_proposee`, et `consolider --appliquer` (etape suivante de la chaine) les fusionne avec
sa trace, donc une fausse fusion se defait (`consolider.defusionner`).
"""

from __future__ import annotations

import re

from .db import connect

TAILLE_FINALE = r"[\s-]+(xxs|xs|s|m|l|xl|xxl|2xl|3xl|4xl|5xl)\s*$"
MARCHANDS = ("labecanerie", "speedway")
ECART_PRIX_MAX = 1.3

_SQL = r"""
CREATE TEMP TABLE _t ON COMMIT DROP AS
SELECT o.product_id, m.code AS marchand, p.brand_code, upper(coalesce(o.raw_size, '')) AS taille,
       regexp_replace(lower(o.raw_title), %(taille_finale)s, '') AS titre
FROM raw_offer o
JOIN product p ON p.id = o.product_id
JOIN merchant m ON m.id = o.merchant_id
WHERE o.is_live AND p.category_id BETWEEN 1 AND 5 AND p.status <> 'merged'
  AND m.code = ANY(%(marchands)s);

CREATE TEMP TABLE _g ON COMMIT DROP AS
SELECT array_agg(DISTINCT product_id ORDER BY product_id) AS ids
FROM _t GROUP BY brand_code, marchand, titre
HAVING count(DISTINCT product_id) = 2;

CREATE TEMP TABLE _sel ON COMMIT DROP AS
SELECT DISTINCT g.ids FROM _g g
JOIN product a ON a.id = g.ids[1] JOIN product b ON b.id = g.ids[2]
JOIN product_stats sa ON sa.product_id = g.ids[1] JOIN product_stats sb ON sb.product_id = g.ids[2]
WHERE a.model_display = b.model_display
  AND least(sa.cheapest, sb.cheapest) > 0
  AND greatest(sa.cheapest, sb.cheapest) / least(sa.cheapest, sb.cheapest) < %(ecart)s
  AND EXISTS (SELECT 1 FROM _t WHERE product_id = g.ids[1] AND taille <> '')
  AND EXISTS (SELECT 1 FROM _t WHERE product_id = g.ids[2] AND taille <> '')
  AND NOT EXISTS (SELECT 1 FROM _t x JOIN _t y ON x.taille = y.taille AND x.taille <> ''
                  WHERE x.product_id = g.ids[1] AND y.product_id = g.ids[2]);

DELETE FROM _sel s WHERE EXISTS (SELECT 1 FROM _sel o WHERE o.ids <> s.ids AND o.ids && s.ids);
"""

_INSCRIRE = """
INSERT INTO fusion_proposee (cle, produit_ids, survivant, nb_fiches, nb_marchands, statut, decide_le)
SELECT md5(ids[1] || ',' || ids[2]), ids::int[],
       (SELECT product_id FROM (SELECT product_id, count(*) n FROM raw_offer
                                WHERE is_live AND product_id = ANY(s.ids)
                                GROUP BY 1) q ORDER BY n DESC, product_id LIMIT 1),
       2, 2, 'validee', now()
FROM _sel s
ON CONFLICT (cle) DO UPDATE SET statut = 'validee', decide_le = now()
WHERE fusion_proposee.statut = 'proposee'
"""


def paires_a_fusionner(inscrire: bool = False) -> int:
    """Nombre de paires de fiches de casque qui sont le meme casque coupe par tailles.

    `inscrire=False` ne modifie rien (la transaction est annulee) ; `True` les inscrit comme
    validees pour `consolider --appliquer`.
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            params = {"taille_finale": TAILLE_FINALE, "marchands": list(MARCHANDS),
                      "ecart": ECART_PRIX_MAX}
            for instruction in _SQL.split(";" + chr(10) * 2):      # psycopg: une instruction par execute
                cur.execute(instruction.strip().rstrip(";"), params)
            cur.execute("SELECT count(*) FROM _sel")
            n = cur.fetchone()[0]
            if inscrire and n:
                cur.execute(_INSCRIRE)
        if inscrire:
            conn.commit()
        else:
            conn.rollback()
        return n
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def titre_sans_taille(titre: str) -> str:
    """Le titre d'un marchand, taille finale retiree : la cle de comparaison de la regle."""
    return re.sub(TAILLE_FINALE, "", titre.lower())
