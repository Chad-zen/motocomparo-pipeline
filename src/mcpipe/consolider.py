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
        conn.commit()
        return {"gtins_eclates": len(gtins), "groupes": len(groupes),
                "retenus": len(retenus), "ecartes_trop_gros": ecartes,
                "nouveaux": nouveaux}
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


def appliquer() -> dict[str, int]:
    """Fusionne les groupes validés (et les proposés si `fusion_auto = oui`).

    Les offres passent sur la fiche survivante ; les autres fiches deviennent
    `merged` avec `merged_into` : elles disparaissent des listes et leur adresse
    redirige vers la survivante. Les liens de variantes périmés sont retirés ;
    `mcpipe relier-tailles` les recrée, puis `freshness` recalcule les prix.
    """
    conn = connect()
    try:
        alias = charger_alias(conn)
        with conn.cursor() as cur:
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
