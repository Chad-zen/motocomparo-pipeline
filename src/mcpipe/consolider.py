"""Regrouper les fiches qui se dédoublent pour un même code-barres.

LE PROBLÈME (16/10/2026). Le `match` incrémental ne regarde que les offres
`unresolved` : une offre neuve dont le code-barres est déjà rattaché ailleurs
fabrique SA propre empreinte d'identité au lieu de rejoindre la fiche
existante. Le casque Shark i3 existait en deux fiches, l'une chez FC-Moto,
Motoblouz et Speedway, l'autre chez La Bécanerie seule : le visiteur ne voyait
jamais les quatre prix ensemble. Mesuré en production : 65 383 codes-barres
vendus par deux marchands ou plus étaient éclatés sur plusieurs fiches.

CE QUE FAIT CE MODULE, EN TROIS TEMPS, ET QUI DÉCIDE :

1. `proposer` repère les codes-barres dont les offres sont sur plusieurs fiches
   et ne retient que ceux où TOUTES les fiches passent les garde-fous du
   rapprochement (marque, rayon, genre, année, couleur, rapport de prix). Les
   fiches reliées par un code-barres forment un groupe ; un groupe de plus de
   `TAILLE_MAX` fiches est écarté, jamais fusionné (fermeture transitive sans
   plafond = risque de méga-fusion). Rien n'est modifié : les groupes sont
   écrits dans `fusion_proposee`.
2. La propriétaire valide ou refuse dans l'écran d'administration. Un réglage
   (`fusion_auto = oui`) valide d'office les groupes sûrs, une fois qu'elle a
   fait confiance à l'échantillon.
3. `appliquer` fusionne ce qui est validé : les offres passent sur la fiche
   survivante, les autres fiches deviennent `merged` (donc invisibles et
   redirigées vers la survivante). Rejouable, à chaque nuit.

LE RISQUE QUE CE PROJET REFUSE LE PLUS est la FAUSSE fusion : deux produits
différents présentés comme un seul. Les garde-fous ci-dessous sont ceux du
`match`, appliqués à la lettre ; ils ne sont jamais assouplis ici.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .db import connect

# Au-delà, un groupe ressemble à une fiche fourre-tout (« Ermax Bulle Haute »,
# 1 314 codes-barres sur une fiche) plutôt qu'à un même produit en doublon.
TAILLE_MAX = 25

# Le rapport de prix du `match` : deux offres sur un même code-barres dont le
# prix varie de plus de 5 fois ne parlent pas du même article.
RAPPORT_PRIX_MAX = 5.0


@dataclass(frozen=True)
class Fiche:
    id: int
    marque: str
    rayon: int
    genre: str
    annee: int | None
    couleur: str
    nb_offres: int = 0


# --- les garde-fous (purs, testés sans base) ---------------------------------

def _base_couleur(code: str | None) -> str:
    """« BK|MAT » -> « BK » ; « unknown » et vide -> «  »."""
    c = (code or "").split("|")[0].strip().upper()
    return "" if c in ("", "UNKNOWN") else c


def marque_canonique(marque: str | None, alias: dict[str, str]) -> str:
    m = (marque or "").strip().lower()
    return alias.get(m, m)


def compatibles(a: Fiche, b: Fiche, alias: dict[str, str]) -> bool:
    """Deux fiches peuvent-elles être le même produit ?

    Marque (alias appliqués) et rayon IDENTIQUES ; âge (adulte/enfant)
    identique et sexe identique ou inconnu ; année identique si les deux la
    portent ; couleur de base identique ou inconnue d'un côté.
    """
    if marque_canonique(a.marque, alias) != marque_canonique(b.marque, alias):
        return False
    if not marque_canonique(a.marque, alias):
        return False
    if a.rayon != b.rayon:
        return False
    sa, aa = (a.genre or "U-A").split("-")[0], (a.genre or "U-A").split("-")[-1]
    sb, ab = (b.genre or "U-A").split("-")[0], (b.genre or "U-A").split("-")[-1]
    if aa != ab:
        return False
    if sa != sb and "U" not in (sa, sb):
        return False
    if a.annee is not None and b.annee is not None and a.annee != b.annee:
        return False
    ca, cb = _base_couleur(a.couleur), _base_couleur(b.couleur)
    if ca and cb and ca != cb:
        return False
    return True


def gtin_sur(fiches: list[Fiche], pmin: float | None, pmax: float | None,
             alias: dict[str, str]) -> bool:
    """Un code-barres peut-il relier ces fiches ? Toutes doivent être
    compatibles DEUX À DEUX, et le prix ne pas varier de plus de 5 fois."""
    if len(fiches) < 2:
        return False
    if pmin and pmax and pmin > 0 and pmax / pmin > RAPPORT_PRIX_MAX:
        return False
    return all(compatibles(a, b, alias)
               for i, a in enumerate(fiches) for b in fiches[i + 1:])


def former_groupes(liens: list[list[int]]) -> list[set[int]]:
    """Fermeture transitive : les fiches reliées par au moins un code-barres sûr."""
    parent: dict[int, int] = {}

    def trouver(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for ids in liens:
        racine = trouver(ids[0])
        for i in ids[1:]:
            parent[trouver(i)] = racine
    groupes: dict[int, set[int]] = {}
    for x in list(parent):
        groupes.setdefault(trouver(x), set()).add(x)
    return list(groupes.values())


def cle_groupe(ids: set[int] | list[int]) -> str:
    return hashlib.md5(",".join(str(i) for i in sorted(ids)).encode()).hexdigest()


def choisir_survivant(fiches: list[Fiche]) -> int:
    """La fiche qui porte le plus d'offres ; à égalité, la plus ancienne."""
    return sorted(fiches, key=lambda f: (-f.nb_offres, f.id))[0].id


# --- les fiches au meme nom, aux mots de type pres ----------------------------

# LE CAS MACNA FLUENT (19/10/2026). FC-Moto ecrit « Macna Fluent Veste textile de
# moto », Speedway « Veste Macna Fluent Noir - Blouson Moto MACNA » : les jetons du
# modele sont {fluent, textile, veste} d'un cote, {blouson, fluent, veste} de
# l'autre, donc deux empreintes et deux fiches. Les tailles XS, M, L, XL et XXL de
# FC-Moto vivaient sur l'une, la S et Speedway sur l'autre.
#
# On ne corrige PAS la normalisation : « blouson », « veste » et « textile » sont
# dans le nom ET l'adresse de 37 005 fiches d'habillement sur 43 169, les
# retirer changerait l'adresse de presque toutes pour en reunir 516 en 256 groupes
# (mesure du 19/10/2026). On propose donc ces regroupements ici, comme ceux des
# codes-barres : la proprietaire valide, la fiche absorbee est redirigee.
#
# `cuir` n'est PAS dans la liste : « Fluent cuir » et « Fluent textile » peuvent
# etre deux produits.
MOTS_DE_TYPE = frozenset(
    "blouson veste jacket textile pantalon pants jeans jean gants gant gloves "
    "bottes botte boots chaussures chaussure combinaison moto motorcycle".split())


def cle_nom(model_display: str | None) -> frozenset[str]:
    """Le nom d'une fiche sans ses mots de type : « Blouson Fluent Veste » et
    « Fluent Textile Veste » donnent tous deux {fluent}."""
    return frozenset(
        w for w in (model_display or "").lower().split() if w not in MOTS_DE_TYPE)


def _liens_par_nom(conn, alias: dict[str, str]) -> list[list[int]]:
    """Les groupes de fiches d'habillement de meme marque, rayon, couleur, genre
    et nom (mots de type exceptes), dont les offres ne sont pas a plus de 5 fois
    l'une de l'autre. Passe par `compatibles`, comme les codes-barres."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.id, p.brand_code, p.category_id, p.genre_age, p.model_year,
                   p.colour_code, p.model_display,
                   count(o.id) AS nb, min(o.price) AS pmin, max(o.price) AS pmax
            FROM product p JOIN raw_offer o ON o.product_id = p.id AND o.is_live
            WHERE p.status <> 'merged' AND p.category_id IN (6, 7, 8, 9, 10)
              AND p.brand_code IS NOT NULL AND o.price > 0
            GROUP BY p.id""")
        lignes = cur.fetchall()
    par_cle: dict[tuple, list[tuple]] = {}
    for pid, marque, rayon, genre, annee, couleur, nom, nb, pmin, pmax in lignes:
        cle = cle_nom(nom)
        if not cle:        # un nom vide de tout sauf de mots de type ne dit rien
            continue
        par_cle.setdefault(
            (marque_canonique(marque, alias), rayon, _base_couleur(couleur), cle), []
        ).append((Fiche(pid, marque, rayon, genre, annee, couleur, nb),
                  float(pmin), float(pmax), (nom or "").lower()))
    liens = []
    for fiches in par_cle.values():
        if len(fiches) < 2 or len(fiches) > TAILLE_MAX:
            continue
        # au moins deux ECRITURES du nom (« blouson fluent veste » / « fluent textile
        # veste ») : des fiches qui portent le meme nom mot pour mot different par
        # autre chose (annee, serie), et ce n'est pas ce regroupement-ci
        if len({nom for _, _, _, nom in fiches}) < 2:
            continue
        pmin = min(a for _, a, _, _ in fiches)
        pmax = max(b for _, _, b, _ in fiches)
        if pmin > 0 and pmax / pmin > RAPPORT_PRIX_MAX:
            continue
        fs = [f for f, _, _, _ in fiches]
        if gtin_sur(fs, pmin, pmax, alias):
            liens.append([f.id for f in fs])
    return liens


# --- avec la base ------------------------------------------------------------

_GTIN_ECLATES = """
SELECT o.gtin, array_agg(DISTINCT o.product_id) AS pids,
       min(o.price) AS pmin, max(o.price) AS pmax
FROM raw_offer o
JOIN merchant m ON m.id = o.merchant_id AND m.gtin_trust = 'trusted'
JOIN product p ON p.id = o.product_id AND p.status <> 'merged'
WHERE o.is_live AND o.gtin IS NOT NULL AND o.product_id IS NOT NULL
GROUP BY o.gtin
HAVING count(DISTINCT o.product_id) > 1
"""


def charger_alias(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT alias, marque FROM marque_alias WHERE statut = 'valide'")
        return {a.lower(): m.lower() for a, m in cur.fetchall()}


_PROPOSITIONS_MARQUES = """
INSERT INTO marque_proposition (a, b, codes_barres, fiches_a, fiches_b, titre_a, titre_b)
WITH g AS (
    SELECT o.gtin, array_agg(DISTINCT sg.brand_code ORDER BY sg.brand_code) AS bs
    FROM raw_offer o
    JOIN merchant m ON m.id = o.merchant_id AND m.gtin_trust = 'trusted'
    JOIN offer_signature sg ON sg.raw_offer_id = o.id
    WHERE o.is_live AND o.gtin IS NOT NULL AND sg.brand_code IS NOT NULL
      AND sg.brand_code <> ''
    GROUP BY o.gtin HAVING count(DISTINCT sg.brand_code) = 2
), paires AS (
    SELECT bs[1] AS a, bs[2] AS b, count(*) AS codes_barres, min(gtin) AS exemple
    FROM g GROUP BY 1, 2 HAVING count(*) >= 3
)
SELECT p.a, p.b, p.codes_barres,
       (SELECT count(*) FROM product WHERE brand_code = p.a AND status <> 'merged'),
       (SELECT count(*) FROM product WHERE brand_code = p.b AND status <> 'merged'),
       (SELECT left(o.raw_title, 60) FROM raw_offer o JOIN offer_signature sg
          ON sg.raw_offer_id = o.id WHERE o.gtin = p.exemple AND sg.brand_code = p.a LIMIT 1),
       (SELECT left(o.raw_title, 60) FROM raw_offer o JOIN offer_signature sg
          ON sg.raw_offer_id = o.id WHERE o.gtin = p.exemple AND sg.brand_code = p.b LIMIT 1)
FROM paires p
ORDER BY p.codes_barres DESC LIMIT 200
"""


def proposer(max_groupes: int | None = None) -> dict[str, int]:
    """Calcule les groupes et les écrit dans `fusion_proposee` (statut proposee).

    Rien d'autre n'est modifié. Un groupe déjà décidé (validé, refusé, appliqué)
    n'est pas touché ; un groupe `proposee` dont la composition a changé
    reçoit une nouvelle clé.
    """
    conn = connect()
    try:
        alias = charger_alias(conn)
        with conn.cursor() as cur:
            cur.execute(_GTIN_ECLATES)
            gtins = cur.fetchall()
            ids = sorted({p for _, pids, _, _ in gtins for p in pids})
            cur.execute("""
                SELECT p.id, p.brand_code, p.category_id, p.genre_age, p.model_year,
                       p.colour_code,
                       (SELECT count(*) FROM raw_offer o
                        WHERE o.product_id = p.id AND o.is_live)
                FROM product p WHERE p.id = ANY(%s)""", (ids,))
            fiches = {r[0]: Fiche(r[0], r[1], r[2], r[3], r[4], r[5], r[6])
                      for r in cur.fetchall()}
        liens = []
        for _, pids, pmin, pmax in gtins:
            fs = [fiches[p] for p in pids if p in fiches]
            if len(fs) == len(pids) and gtin_sur(fs, float(pmin or 0), float(pmax or 0), alias):
                liens.append(list(pids))
        par_codes_barres = len(liens)
        liens += _liens_par_nom(conn, alias)
        par_nom = len(liens) - par_codes_barres
        # les fiches reliees par le nom ne sont pas dans `fiches` (chargees pour
        # les seuls codes-barres) : on complete avant de choisir le survivant
        manquants = sorted({i for lien in liens for i in lien} - fiches.keys())
        if manquants:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.id, p.brand_code, p.category_id, p.genre_age, p.model_year,
                           p.colour_code,
                           (SELECT count(*) FROM raw_offer o
                            WHERE o.product_id = p.id AND o.is_live)
                    FROM product p WHERE p.id = ANY(%s)""", (manquants,))
                fiches.update({r[0]: Fiche(r[0], r[1], r[2], r[3], r[4], r[5], r[6])
                               for r in cur.fetchall()})
        groupes = former_groupes(liens)
        ecartes = sum(1 for g in groupes if len(g) > TAILLE_MAX)
        retenus = [g for g in groupes if 2 <= len(g) <= TAILLE_MAX]
        if max_groupes:
            retenus = retenus[:max_groupes]
        nouveaux = 0
        with conn.cursor() as cur:
            # une proposition jamais décidée est recalculée : on repart propre
            cur.execute("DELETE FROM fusion_proposee WHERE statut = 'proposee'")
            for g in retenus:
                fs = [fiches[i] for i in g]
                cur.execute("""
                    SELECT count(DISTINCT o.merchant_id) FROM raw_offer o
                    WHERE o.product_id = ANY(%s) AND o.is_live""", (sorted(g),))
                marchands = cur.fetchone()[0]
                cur.execute("""
                    INSERT INTO fusion_proposee
                        (cle, produit_ids, survivant, nb_fiches, nb_marchands)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (cle) DO NOTHING""",
                            (cle_groupe(g), sorted(g), choisir_survivant(fs),
                             len(g), marchands))
                nouveaux += cur.rowcount
        with conn.cursor() as cur:
            cur.execute("DELETE FROM marque_proposition")
            cur.execute(_PROPOSITIONS_MARQUES)
        conn.commit()
        return {"gtins_eclates": len(gtins), "groupes": len(groupes),
                "retenus": len(retenus), "ecartes_trop_gros": ecartes,
                "nouveaux": nouveaux, "par_nom": par_nom}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_FUSIONNER = """
UPDATE raw_offer SET product_id = %(s)s
WHERE product_id = ANY(%(autres)s);
"""
_DELIER_VARIANTES_DE_L_AUTRE = """
DELETE FROM offer_variant_link l
USING raw_offer o, variant v
WHERE l.raw_offer_id = o.id AND v.id = l.variant_id AND v.product_id <> o.product_id
  AND o.product_id = %(s)s
"""


_TRACE = """
CREATE TABLE IF NOT EXISTS fusion_trace (
    fusion_id          bigint NOT NULL,
    genre              text   NOT NULL CHECK (genre IN ('offre', 'fiche')),
    ref_id             bigint NOT NULL,
    ancien_product_id  bigint,
    ancien_status      text,
    ancienne_marque    text,
    ancien_merged_into bigint,
    trace_le           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (fusion_id, genre, ref_id)
)"""

_TRACER_OFFRES = """
INSERT INTO fusion_trace (fusion_id, genre, ref_id, ancien_product_id)
SELECT %(f)s, 'offre', id, product_id FROM raw_offer WHERE product_id = ANY(%(autres)s)
ON CONFLICT DO NOTHING"""

_TRACER_FICHES = """
INSERT INTO fusion_trace (fusion_id, genre, ref_id, ancien_status, ancienne_marque, ancien_merged_into)
SELECT %(f)s, 'fiche', id, status, brand_code, merged_into FROM product WHERE id = ANY(%(toutes)s)
ON CONFLICT DO NOTHING"""


def appliquer(cles: list[str] | None = None) -> dict[str, int]:
    """Fusionne les groupes validés (et les proposés si `fusion_auto = oui`).

    `cles` : ne traiter QUE ces groupes (par `cle`), jamais les autres validés ni
    la file automatique. C'est ce qu'utilise `fusion-repli`.

    Avant de toucher une fiche, l'état d'avant est écrit dans `fusion_trace` (offres
    et fiches) : sans cette trace, une fausse fusion ne se défait pas. Voir `defusionner`.

    Les offres passent sur la fiche survivante ; les autres fiches deviennent
    `merged` avec `merged_into` : elles disparaissent des listes et leur adresse
    redirige vers la survivante. Les liens de variantes périmés sont retirés ;
    `mcpipe relier-tailles` les recrée, puis `freshness` recalcule les prix.
    """
    conn = connect()
    try:
        alias = charger_alias(conn)
        with conn.cursor() as cur:
            cur.execute(_TRACE)
            if cles is not None:
                cur.execute("SELECT id, produit_ids, survivant FROM fusion_proposee "
                            "WHERE statut = 'validee' AND cle = ANY(%s)", (list(cles),))
            else:
                cur.execute("SELECT valeur FROM reglage WHERE cle = 'fusion_auto'")
                r = cur.fetchone()
                auto = bool(r and r[0] == "oui")
                cur.execute(
                    "SELECT id, produit_ids, survivant FROM fusion_proposee "
                    "WHERE statut = 'validee'" + (" OR statut = 'proposee'" if auto else ""))
            a_faire = cur.fetchall()
        fusionnees = 0
        for fid, pids, survivant in a_faire:
            autres = [p for p in pids if p != survivant]
            with conn.cursor() as cur:
                # sécurité : une fiche déjà fusionnée ailleurs entre ses pairs
                cur.execute("SELECT id FROM product WHERE id = ANY(%s) AND status <> 'merged'",
                            (list(pids),))
                vivantes = {x for (x,) in cur.fetchall()}
                if survivant not in vivantes:
                    cur.execute("UPDATE fusion_proposee SET statut = 'refusee', decide_le = now() "
                                "WHERE id = %s", (fid,))
                    continue
                autres = [p for p in autres if p in vivantes]
                if not autres:
                    cur.execute("UPDATE fusion_proposee SET statut = 'appliquee', decide_le = now() "
                                "WHERE id = %s", (fid,))
                    continue
                cur.execute(_TRACER_OFFRES, {"f": fid, "autres": autres})
                cur.execute(_TRACER_FICHES, {"f": fid, "toutes": [survivant, *autres]})
                cur.execute(_FUSIONNER, {"s": survivant, "autres": autres})
                cur.execute(_DELIER_VARIANTES_DE_L_AUTRE, {"s": survivant})
                cur.execute("UPDATE product SET status = 'merged', merged_into = %s "
                            "WHERE id = ANY(%s)", (survivant, autres))
                # la marque affichée est la marque canonique
                cur.execute("SELECT brand_code FROM product WHERE id = %s", (survivant,))
                marque = marque_canonique(cur.fetchone()[0], alias)
                cur.execute("UPDATE product SET brand_code = %s WHERE id = %s",
                            (marque, survivant))
                cur.execute("UPDATE fusion_proposee SET statut = 'appliquee', decide_le = now() "
                            "WHERE id = %s", (fid,))
                fusionnees += len(autres)
            conn.commit()
        return {"groupes": len(a_faire), "fiches_fusionnees": fusionnees}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def defusionner(fusion_id: int) -> dict[str, int]:
    """Défait une fusion appliquée, d'après `fusion_trace`.

    Remet chaque offre tracée sur son ancienne fiche, redonne aux fiches leur statut,
    leur marque et leur `merged_into` d'avant, puis marque la fusion `refusee` (la même
    clé ne sera donc jamais reproposée). Les offres ARRIVÉES depuis la fusion ne sont pas
    tracées : elles restent sur la survivante. Lancer ensuite `relier-tailles` et `freshness`.
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE raw_offer o SET product_id = t.ancien_product_id "
                        "FROM fusion_trace t WHERE t.fusion_id = %s AND t.genre = 'offre' "
                        "AND t.ref_id = o.id", (fusion_id,))
            offres = cur.rowcount
            cur.execute("UPDATE product p SET status = t.ancien_status, brand_code = t.ancienne_marque, "
                        "merged_into = t.ancien_merged_into FROM fusion_trace t "
                        "WHERE t.fusion_id = %s AND t.genre = 'fiche' AND t.ref_id = p.id", (fusion_id,))
            fiches = cur.rowcount
            cur.execute("DELETE FROM offer_variant_link l USING raw_offer o, variant v "
                        "WHERE l.raw_offer_id = o.id AND v.id = l.variant_id AND v.product_id <> o.product_id "
                        "AND o.id IN (SELECT ref_id FROM fusion_trace WHERE fusion_id = %s AND genre = 'offre')",
                        (fusion_id,))
            cur.execute("UPDATE fusion_proposee SET statut = 'refusee', decide_le = now() WHERE id = %s",
                        (fusion_id,))
        conn.commit()
        return {"offres": offres, "fiches": fiches}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
