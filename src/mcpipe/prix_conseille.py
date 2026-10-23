"""Le prix public conseillé (PVC) de chaque fiche, relevé dans les prix barrés des flux (23/10/2026).

D'OU VIENT LE CHIFFRE. Trois flux donnent un prix « avant remise » : Motoblouz (`crossed price`), Speedway
et La Becanerie (`price_norebate`). Speedway l'etiquette lui-meme « prix public conseille » et precise que
c'est le tarif catalogue du fabricant. Mesure du 23/10 : sur 5 209 produits vendus par Motoblouz ET Speedway,
les deux donnent le meme prix barre (a 1 %) dans 87 % des cas. La Becanerie est presque toujours plus bas
que les deux autres : elle confirme, elle ne decide jamais seule.

LA REGLE (trois experts consultes le 23/10/2026 : droit de la consommation, qualite des donnees, confiance
du visiteur). Un PVC n'est publie que s'il est SOURCE :
  - palier 1 : au moins deux marchands (Motoblouz, Speedway, La Becanerie) donnent la meme valeur a 1 % ;
  - palier 2 : Speedway seul, qui l'etiquette « prix public conseille », et seulement si le PVC reste entre
    1,03 et 1,5 fois le meilleur prix (au-dela, un prix barre est probablement un tarif perime) ;
  - Motoblouz seul : PAS publie, rien ne dit que son prix barre n'est pas un prix deja solde ;
  - desaccord entre marchands (aucune paire a 1 %) : pas de PVC. Un PVC trop haut fabrique une fausse remise.
Le palier 1 est borne a 3 fois le meilleur prix : au-dela, c'est une erreur de flux plus qu'un tarif.

Rien dans ce module n'est affiche tant que le site ne lit pas la table `prix_conseille`.
"""

from __future__ import annotations

from .db import connect

SOURCES = ("motoblouz", "speedway", "labecanerie")
TOLERANCE = 0.01
PALIER1_MAX = 3.0
PALIER2_MIN, PALIER2_MAX = 1.03, 1.5


def choisir_pvc(refs: dict[str, float], meilleur_prix: float | None) -> tuple[float, int, str] | None:
    """Le PVC d'une fiche : (prix, palier, marchands) ou None.

    `refs` : marchand -> prix barre releve. `meilleur_prix` : le moins cher du moment (le garde-fou
    compare le PVC a ce qu'un visiteur paiera).
    """
    refs = {m: v for m, v in refs.items() if m in SOURCES and v and v > 0}
    if not refs or not meilleur_prix or meilleur_prix <= 0:
        return None
    marchands = sorted(refs)
    # palier 1 : la plus grande famille de marchands d'accord a 1 %
    meilleure: tuple[int, float, list[str]] | None = None
    for m in marchands:
        famille = [x for x in marchands if abs(refs[x] - refs[m]) <= TOLERANCE * max(refs[x], refs[m])]
        valeur = max(refs[x] for x in famille)
        if len(famille) >= 2 and (meilleure is None or (len(famille), valeur) > (meilleure[0], meilleure[1])):
            meilleure = (len(famille), valeur, famille)
    if meilleure:
        prix = round(meilleure[1], 2)
        if prix <= meilleur_prix * PALIER1_MAX:
            return prix, 1, "+".join(meilleure[2])
        return None
    # pas de paire : Speedway seul, et seulement s'il est SEUL a avoir un prix barre
    if marchands == ["speedway"]:
        prix = round(refs["speedway"], 2)
        if PALIER2_MIN * meilleur_prix <= prix <= PALIER2_MAX * meilleur_prix:
            return prix, 2, "speedway"
    return None


_CREER = """
CREATE TABLE IF NOT EXISTS prix_conseille (
    product_id  bigint PRIMARY KEY,
    prix        numeric(10, 2) NOT NULL,
    palier      smallint NOT NULL,
    sources     text NOT NULL,
    calcule_le  timestamptz NOT NULL DEFAULT now()
)
"""

_PRIX = r"""
CREATE TEMP TABLE _o ON COMMIT DROP AS
SELECT 'labecanerie' AS m, row->>'gtin' AS g,
       nullif(regexp_replace(row->>'price', '[^0-9.]', '', 'g'), '')::numeric AS courant,
       nullif(regexp_replace(row->>'price_norebate', '[^0-9.]', '', 'g'), '')::numeric AS ref
FROM stg_feed_row WHERE merchant_id = (SELECT id FROM merchant WHERE code = 'labecanerie')
UNION ALL
SELECT 'speedway', row->>'gtin',
       nullif(regexp_replace(row->>'price', '[^0-9.]', '', 'g'), '')::numeric,
       nullif(regexp_replace(row->>'price_norebate', '[^0-9.]', '', 'g'), '')::numeric
FROM stg_feed_row WHERE merchant_id = (SELECT id FROM merchant WHERE code = 'speedway')
UNION ALL
SELECT 'motoblouz', row->>'universal reference',
       nullif(regexp_replace(row->>'price', '[^0-9.]', '', 'g'), '')::numeric,
       nullif(regexp_replace(row->>'crossed price', '[^0-9.]', '', 'g'), '')::numeric
FROM stg_feed_row WHERE merchant_id = (SELECT id FROM merchant WHERE code = 'motoblouz')
"""

_RELEVES = """
SELECT ro.product_id, o.m, round(o.ref, 2) AS ref, count(*) AS n
FROM _o o
JOIN merchant mm ON mm.code = o.m
JOIN raw_offer ro ON ro.merchant_id = mm.id AND ro.raw_gtin = o.g AND ro.is_live
                 AND ro.linked_status = 'linked' AND ro.product_id IS NOT NULL
WHERE o.g IS NOT NULL AND o.g <> '' AND o.courant > 0 AND o.ref > o.courant * 1.005
GROUP BY 1, 2, 3
"""


def calculer(ecrire: bool = False) -> dict[str, int]:
    """Calcule le PVC de chaque fiche ; `ecrire=True` remplace le contenu de `prix_conseille`.

    Un marchand qui a plusieurs prix barres pour une meme fiche (tailles) garde le plus frequent.
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_CREER)
            cur.execute(_PRIX)
            cur.execute(_RELEVES)
            par_fiche: dict[int, dict[str, tuple[int, float]]] = {}
            for pid, m, ref, n in cur.fetchall():
                actuel = par_fiche.setdefault(pid, {}).get(m)
                if actuel is None or (n, ref) > actuel:
                    par_fiche[pid][m] = (n, float(ref))
            cur.execute("SELECT product_id, cheapest FROM product_stats WHERE cheapest IS NOT NULL")
            meilleurs = {pid: float(p) for pid, p in cur.fetchall()}
            choisis: list[tuple[int, float, int, str]] = []
            bilan = {"fiches_avec_prix_barre": len(par_fiche), "palier_1": 0, "palier_2": 0}
            for pid, par_m in par_fiche.items():
                r = choisir_pvc({m: v for m, (_, v) in par_m.items()}, meilleurs.get(pid))
                if r:
                    choisis.append((pid, r[0], r[1], r[2]))
                    bilan[f"palier_{r[1]}"] += 1
            if ecrire:
                cur.execute("DELETE FROM prix_conseille")
                cur.executemany(
                    "INSERT INTO prix_conseille (product_id, prix, palier, sources) VALUES (%s, %s, %s, %s)",
                    choisis)
        if ecrire:
            conn.commit()
        else:
            conn.rollback()
        return bilan
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
