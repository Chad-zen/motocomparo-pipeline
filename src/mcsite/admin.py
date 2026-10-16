"""What the site knows about itself.

The owner runs this project alone. Leaving WordPress means leaving its admin
screen too, and without a replacement every question — did the feeds run? are
the prices fresh? how much is waiting in review? — needs a developer and a SQL
prompt. That is the cost of going autonomous, and this is the answer to it.

Read-only by construction: every statement below is a SELECT. Nothing here can
change the catalogue, so it can be opened without fear.

⚠️ It exposes counts, merchant names and pipeline timings. Harmless on a laptop
or a home network; before this reaches a public address it needs a password.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

# How long a feed may go unfetched before it is worth saying so out loud. The
# pipeline is meant to run daily; two days means something is stuck.
ALERTE_FLUX_HEURES = 36


def _rows(conn: psycopg.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def _row(conn: psycopg.Connection, sql: str, args: tuple = ()) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchone() or {}


def flux(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """One line per merchant: what it sent, when, and what became of it.

    `derniere_vue` is when `normalize` last processed that merchant, which is
    NOT when the merchant published — a known flaw, recorded in
    docs/REPRENDRE-ICI.md. Both are shown so the gap is visible rather than
    hidden behind one reassuring number.
    """
    return _rows(conn, """
        SELECT m.code,
               m.gtin_trust,
               f.finished_at            AS dernier_chargement,
               f.row_count              AS lignes_chargees,
               count(o.id) FILTER (WHERE o.is_live)                        AS offres_vivantes,
               count(o.id) FILTER (WHERE o.linked_status = 'linked'
                                     AND o.is_live)                        AS rattachees,
               count(o.id) FILTER (WHERE o.linked_status <> 'linked'
                                     AND o.is_live)                        AS en_attente,
               count(o.id) FILTER (WHERE o.price IS NULL AND o.is_live)    AS sans_prix,
               max(o.last_seen)                                            AS derniere_vue
        FROM merchant m
        LEFT JOIN raw_offer o ON o.merchant_id = m.id
        LEFT JOIN LATERAL (
            SELECT finished_at, row_count FROM feed_run r
            WHERE r.merchant_id = m.id AND r.status = 'ok'
            ORDER BY r.finished_at DESC LIMIT 1
        ) f ON true
        GROUP BY m.code, m.gtin_trust, f.finished_at, f.row_count
        ORDER BY count(o.id) FILTER (WHERE o.is_live) DESC
    """)


def catalogue(conn: psycopg.Connection) -> dict[str, Any]:
    """The headline figures, the ones worth looking at every morning."""
    return _row(conn, """
        SELECT (SELECT count(*) FROM product)                               AS fiches,
               (SELECT count(*) FROM product_stats
                 WHERE merchant_count >= 2)                                 AS comparables,
               (SELECT count(*) FROM product_stats
                 WHERE merchant_count >= 3)                                 AS trois_marchands,
               (SELECT count(*) FROM product WHERE min_price IS NOT NULL)    AS avec_prix,
               (SELECT count(*) FROM product WHERE status = 'stale')         AS perimees,
               (SELECT count(*) FROM product
                 WHERE colour_code = 'unknown')                             AS sans_couleur,
               (SELECT count(*) FROM variant)                               AS variantes,
               (SELECT count(*) FROM match_review_queue
                 WHERE status = 'pending')                                  AS en_revue
    """)


def prix(conn: psycopg.Connection) -> dict[str, Any]:
    """Freshness, which is the one promise a comparison site makes."""
    return _row(conn, """
        SELECT count(*) FILTER (WHERE o.is_live)                            AS offres,
               count(*) FILTER (WHERE o.is_live AND o.price IS NOT NULL)     AS avec_prix,
               count(*) FILTER (WHERE o.is_live
                                  AND o.last_seen >= now() - interval '24 hours') AS fraiches,
               count(*) FILTER (WHERE o.is_live AND o.in_stock IS FALSE)     AS en_rupture,
               min(o.price) FILTER (WHERE o.is_live)                         AS prix_mini,
               max(o.price) FILTER (WHERE o.is_live)                         AS prix_maxi,
               (SELECT max(observed_on) FROM price_history)                  AS dernier_releve,
               (SELECT count(DISTINCT observed_on) FROM price_history)       AS jours_historique
        FROM raw_offer o
    """)


def alertes(conn: psycopg.Connection) -> list[dict[str, str]]:
    """Only things that are actually wrong, each with the number that proves it.

    A dashboard that cries wolf gets ignored, so a line appears here only when a
    threshold is crossed — never as a permanent reminder of a known limitation.
    """
    out: list[dict[str, str]] = []
    maintenant = datetime.now(UTC)

    for f in flux(conn):
        if f["dernier_chargement"] is None:
            out.append({"niveau": "grave", "quoi": f"{f['code']} : aucun chargement enregistré"})
            continue
        heures = (maintenant - f["dernier_chargement"]).total_seconds() / 3600
        if heures > ALERTE_FLUX_HEURES:
            out.append({
                "niveau": "grave" if heures > 72 else "attention",
                "quoi": f"{f['code']} : flux vieux de {heures / 24:.1f} jours",
            })
        if f["offres_vivantes"] and not f["rattachees"]:
            out.append({
                "niveau": "attention",
                "quoi": f"{f['code']} : {f['offres_vivantes']:,} offres, aucune rattachée",
            })

    p = prix(conn)
    if p.get("offres") and p.get("fraiches", 0) < p["offres"] * 0.9:
        manquant = p["offres"] - p["fraiches"]
        out.append({"niveau": "grave", "quoi": f"{manquant:,} offres ont un prix de plus de 24 h"})
    if p.get("avec_prix", 0) < p.get("offres", 0):
        out.append({
            "niveau": "attention",
            "quoi": f"{p['offres'] - p['avec_prix']:,} offres sans prix lisible",
        })

    v = {"n": _melanges_categories(conn)}
    if v.get("n"):
        out.append({"niveau": "grave", "quoi": f"{v['n']:,} fiches mélangent deux catégories"})

    if not out:
        out.append({"niveau": "ok", "quoi": "Rien à signaler."})
    return out


# Le compte des fiches qui mélangent deux catégories balaie 600 000 offres
# jointes à autant de signatures : vingt secondes, à chaque ouverture du tableau
# de bord. Or il ne bouge qu'au passage du pipeline, une fois par jour. Gardé
# dix minutes en mémoire : la page passe de vingt secondes à instantanée, et le
# chiffre reste juste à dix minutes près — ce qui est sans conséquence pour une
# alerte qu'on lit le matin.
_MELANGES: tuple[float, int] | None = None
_MELANGES_TTL = 600.0


def _melanges_categories(conn: psycopg.Connection) -> int:
    global _MELANGES
    import time as _t

    if _MELANGES is not None and _t.monotonic() - _MELANGES[0] < _MELANGES_TTL:
        return _MELANGES[1]
    n = _row(conn, """
        SELECT count(*) AS n FROM (
            SELECT o.product_id FROM raw_offer o
            JOIN offer_signature s ON s.raw_offer_id = o.id
            WHERE o.linked_status = 'linked' AND o.product_id IS NOT NULL
              AND s.category_id <> 25
            GROUP BY o.product_id HAVING count(DISTINCT s.category_id) > 1
        ) t
    """).get("n", 0)
    _MELANGES = (_t.monotonic(), n)
    return n


def top_marques(conn: psycopg.Connection, limit: int = 10) -> list[dict[str, Any]]:
    return _rows(conn, """
        SELECT p.brand_code, count(*) AS fiches,
               count(*) FILTER (WHERE s.merchant_count >= 2) AS comparables
        FROM product p JOIN product_stats s ON s.product_id = p.id
        WHERE p.brand_code IS NOT NULL AND p.brand_code <> ''
        GROUP BY p.brand_code ORDER BY count(*) DESC LIMIT %s
    """, (limit,))


def revue(conn: psycopg.Connection, limit: int = 12) -> list[dict[str, Any]]:
    """The head of the review queue — what a human would look at first."""
    return _rows(conn, """
        SELECT q.review_key, q.kind, q.priority,
               array_length(q.raw_offer_ids, 1) AS offres,
               q.signals -> 0 ->> 'title' AS exemple
        FROM match_review_queue q
        WHERE q.status = 'pending'
        ORDER BY q.priority, q.id DESC LIMIT %s
    """, (limit,))


def codes_promo(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Every code, live or not, most urgent first.

    Expired codes stay listed rather than disappearing: seeing « expiré hier »
    is what makes one think to renew it. They are simply no longer served to
    visitors.
    """
    return _rows(conn, """
        SELECT c.id, m.code AS marchand, c.code, c.libelle, c.url,
               c.debut_le, c.fin_le, c.retire_le, c.source, c.conditions,
               c.vu_le,
               (c.retire_le IS NULL AND c.debut_le <= current_date
                AND c.fin_le >= current_date)                 AS actif,
               c.fin_le - current_date                        AS jours_restants
        FROM code_promo c JOIN merchant m ON m.id = c.merchant_id
        ORDER BY (c.retire_le IS NOT NULL), c.fin_le
    """)


def marchands(conn: psycopg.Connection) -> list[dict[str, Any]]:
    return _rows(conn, "SELECT id, code FROM merchant ORDER BY code")


def messages(conn: psycopg.Connection, limit: int = 30) -> list[dict[str, Any]]:
    """Les messages reçus par la page Contact, non traités d'abord.

    Ils vivent ici et pas dans une boîte mail : le site n'a pas de serveur
    d'envoi, et une adresse affichée en clair sur une page publique est aspirée
    par les robots en quelques jours.
    """
    return _rows(conn, """
        SELECT id, sujet, corps, email, page, recu_le, traite_le
        FROM message_contact
        ORDER BY (traite_le IS NOT NULL), recu_le DESC
        LIMIT %s
    """, (limit,))


# --- regroupements de fiches et alias de marque (16/10/2026) -------------------
#
# Premiers écrans où la propriétaire DÉCIDE au lieu de lire : ce qui s'y écrit
# (`fusion_proposee`, `marque_alias`, `reglage`) est lu par le pipeline de nuit.
# Rien ici ne touche directement une fiche : la fusion se fait la nuit suivante,
# `mcpipe consolider --appliquer`, après la décision.

def regroupements_compte(conn: psycopg.Connection) -> dict[str, Any]:
    lignes = _rows(conn, "SELECT statut, count(*) AS n, coalesce(sum(nb_fiches), 0) AS fiches "
                         "FROM fusion_proposee GROUP BY statut")
    par = {r["statut"]: r for r in lignes}
    auto = _row(conn, "SELECT valeur FROM reglage WHERE cle = 'fusion_auto'")
    return {
        "proposees": int(par.get("proposee", {}).get("n", 0)),
        "fiches_proposees": int(par.get("proposee", {}).get("fiches", 0)),
        "validees": int(par.get("validee", {}).get("n", 0)),
        "refusees": int(par.get("refusee", {}).get("n", 0)),
        "appliquees": int(par.get("appliquee", {}).get("n", 0)),
        "auto": auto.get("valeur") == "oui",
    }


def regroupements_echantillon(conn: psycopg.Connection, limite: int = 8) -> list[dict[str, Any]]:
    """Des groupes tirés AU HASARD, pas les premiers : relire un échantillon
    aléatoire est ce qui a permis de mesurer « 0 fausse fusion sur 25 »."""
    groupes = _rows(conn, """
        SELECT id, produit_ids, survivant, nb_fiches, nb_marchands
        FROM fusion_proposee WHERE statut = 'proposee'
        ORDER BY random() LIMIT %s""", (limite,))
    for g in groupes:
        g["fiches"] = _rows(conn, """
            SELECT p.id, p.slug, upper(p.brand_code) AS marque, p.model_display,
                   p.colour_code, p.genre_age, p.model_year, c.label_fr AS rayon,
                   s.image_url, s.best_title, s.cheapest,
                   (SELECT string_agg(DISTINCT m.code, ', ')
                    FROM raw_offer o JOIN merchant m ON m.id = o.merchant_id
                    WHERE o.product_id = p.id AND o.is_live) AS marchands,
                   (SELECT count(DISTINCT o.gtin) FROM raw_offer o
                    WHERE o.product_id = p.id AND o.is_live) AS codes_barres
            FROM product p
            JOIN category c ON c.id = p.category_id
            LEFT JOIN product_stats s ON s.product_id = p.id
            WHERE p.id = ANY(%s)
            ORDER BY (p.id = %s) DESC, p.id""", (g["produit_ids"], g["survivant"]))
    return groupes


def marques_alias(conn: psycopg.Connection) -> list[dict[str, Any]]:
    return _rows(conn, "SELECT alias, marque, statut, cree_le FROM marque_alias "
                       "ORDER BY statut, marque, alias")


def marques_propositions(conn: psycopg.Connection, limite: int = 30) -> list[dict[str, Any]]:
    """Les paires de marques écrites différemment pour un MÊME code-barres.

    Un code-barres est un identifiant d'article : s'il porte « rg » chez un
    marchand et « rgracing » chez un autre, c'est presque toujours la même
    marque. Calculées chaque nuit par `mcpipe consolider` (le calcul balaie
    toutes les offres, trop long pour une page) ; celles déjà décidées (alias
    validé ou refusé) ne reviennent pas.
    """
    return _rows(conn, """
        SELECT p.a, p.b, p.codes_barres, p.fiches_a, p.fiches_b, p.titre_a, p.titre_b
        FROM marque_proposition p
        WHERE NOT EXISTS (SELECT 1 FROM marque_alias x
                          WHERE (x.alias = p.a AND x.marque = p.b)
                             OR (x.alias = p.b AND x.marque = p.a))
        ORDER BY p.codes_barres DESC LIMIT %s""", (limite,))


# --- fiches sans matière, saison ou homologation (16/10/2026) ------------------
#
# Calculées chaque nuit par `mcpipe couverture`. La propriétaire peut y écrire
# la valeur qu'elle connaît : source `manuel`, la première dans l'ordre de
# confiance, jamais effacée par le recalcul de nuit.

_CASQUES = (1, 2, 3, 4, 5)
_BLOUSONS = (6, 10)

# Ce qu'on peut saisir, par famille de rayon : (nom stocké, valeurs proposées).
# Les noms stockés sont ceux que lisent les filtres du site (`_CARAC_SQL`).
SAISONS = [("ete", "Été"), ("mi-saison", "Mi-saison"), ("hiver", "Hiver"),
           ("toutes-saisons", "Toutes saisons")]
MATIERES_TEXTILE = [("textile", "Textile"), ("cuir", "Cuir"),
                    ("cuir et textile", "Cuir et textile"),
                    ("synthétique", "Synthétique"), ("denim", "Denim")]
MATIERES_CALOTTE = [("polycarbonate", "Polycarbonate"), ("composite", "Composite"),
                    ("carbone", "Carbone"), ("thermoplastique", "Thermoplastique"),
                    ("fibre", "Fibre")]
CLASSES = [("AAA", "Classe AAA"), ("AA", "Classe AA"), ("A", "Classe A"),
           ("B", "Classe B"), ("C", "Classe C")]


def choix_pour(categorie: int) -> dict[str, dict[str, Any]]:
    """Les champs saisissables pour une fiche de ce rayon, et où les écrire."""
    if categorie in _CASQUES:
        return {"matiere": {"nom": "calotte", "choix": MATIERES_CALOTTE},
                "homologation": {"nom": "homologation",
                                 "choix": [("22.06", "ECE 22.06"), ("22.05", "ECE 22.05")]}}
    out: dict[str, dict[str, Any]] = {}
    if categorie in (6, 7, 8, 10):
        out["saison"] = {"nom": "saison", "choix": SAISONS}
    if categorie in _BLOUSONS:
        out["matiere"] = {"nom": "matiere_coque",
                          "choix": [("textile", "Textile"), ("cuir", "Cuir"),
                                    ("cuir-textile", "Cuir et textile")]}
        out["homologation"] = {"nom": "classe_protection", "choix": CLASSES}
    elif categorie == 7:
        out["matiere"] = {"nom": "matiere", "choix": MATIERES_TEXTILE}
        out["homologation"] = {"nom": "homologation", "choix": CLASSES}
    elif categorie == 8:
        out["matiere"] = {"nom": "matiere", "choix": MATIERES_TEXTILE[:4]}
        out["homologation"] = {"nom": "homologation",
                               "choix": [("EN 13594", "EN 13594"), ("CE", "CE")]}
    elif categorie == 9:
        out["matiere"] = {"nom": "matiere", "choix": MATIERES_TEXTILE[:4]}
        out["homologation"] = {"nom": "homologation",
                               "choix": [("EN 13634", "EN 13634"), ("CE", "CE")]}
    return out


_RAYONS_SAISON = {"Blousons & vestes", "Gants", "Pantalons", "Combinaisons"}


def couverture_par_rayon(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Le pourcentage renseigné, rayon par rayon ; `None` quand la caractéristique
    n'a pas de sens pour le rayon (saison d'un casque, matière d'une pièce)."""
    lignes = _rows(conn, "SELECT rayon, produits, saison, matiere, homologation, calcule_le "
                         "FROM couverture_caracteristique ORDER BY produits DESC")
    sortie = []
    for l in lignes:
        if not (l["matiere"] or l["homologation"] or l["saison"]):
            continue                      # aucun extracteur ne lit ce rayon
        n = l["produits"] or 1
        sortie.append({
            "rayon": l["rayon"], "produits": l["produits"],
            "saison": round(100 * l["saison"] / n) if l["rayon"] in _RAYONS_SAISON else None,
            "matiere": round(100 * l["matiere"] / n),
            "homologation": round(100 * l["homologation"] / n),
        })
    return sortie


def incompletes_rayons(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Les rayons qui ont des fiches incomplètes, avec leur nombre."""
    return _rows(conn, """
        SELECT c.id, c.label_fr AS rayon, count(*) AS n
        FROM fiche_incomplete f JOIN category c ON c.id = f.categorie
        GROUP BY c.id, c.label_fr ORDER BY count(*) DESC""")


def incompletes(conn: psycopg.Connection, rayon: int | None, manque: str | None,
                page: int = 1, par_page: int = 25) -> tuple[list[dict[str, Any]], int]:
    """Les fiches sans caractéristiques, les plus comparées d'abord : ce sont
    celles que le plus de visiteurs voient."""
    args: dict[str, Any] = {"lim": par_page, "off": (page - 1) * par_page}
    ou = "TRUE"
    if rayon:
        ou += " AND f.categorie = %(rayon)s"
        args["rayon"] = rayon
    if manque in ("saison", "matiere", "homologation"):
        ou += " AND %(manque)s = ANY(f.manque)"
        args["manque"] = manque
    total = _row(conn, f"SELECT count(*) AS n FROM fiche_incomplete f WHERE {ou}", args).get("n", 0)
    lignes = _rows(conn, f"""
        SELECT f.product_id, f.categorie, f.manque, f.marchands,
               p.slug, upper(p.brand_code) AS marque, s.best_title, s.image_url,
               s.cheapest, c.label_fr AS rayon
        FROM fiche_incomplete f
        JOIN product p ON p.id = f.product_id AND p.status <> 'merged'
        JOIN category c ON c.id = f.categorie
        LEFT JOIN product_stats s ON s.product_id = f.product_id
        WHERE {ou}
        ORDER BY f.marchands DESC, f.product_id
        LIMIT %(lim)s OFFSET %(off)s""", args)
    for ligne in lignes:
        ligne["champs"] = {k: v for k, v in choix_pour(ligne["categorie"]).items()
                           if k in ligne["manque"]}
    return lignes, int(total)


def enregistrer_caracteristiques(conn: psycopg.Connection, product_id: int,
                                 valeurs: dict[str, str]) -> int:
    """Écrit les valeurs saisies pour UNE fiche (source `manuel`).

    Seules les valeurs proposées pour le rayon de la fiche sont acceptées : un
    formulaire détourné ne peut pas écrire autre chose. Rend le nombre de
    caractéristiques écrites ; la fiche sort de la liste des incomplètes.
    """
    fiche = _row(conn, "SELECT category_id FROM product WHERE id = %s AND status <> 'merged'",
                 (product_id,))
    if not fiche:
        return 0
    champs = choix_pour(fiche["category_id"])
    ecrites = 0
    for champ, valeur in valeurs.items():
        spec = champs.get(champ)
        if not spec or valeur not in {v for v, _ in spec["choix"]}:
            continue
        conn.execute("""
            INSERT INTO product_caracteristique (product_id, nom, valeur, source, confiance)
            VALUES (%s, %s, %s, 'manuel', 'saisie')
            ON CONFLICT (product_id, nom, source) DO UPDATE
               SET valeur = excluded.valeur, calcule_le = now()""",
                     (product_id, spec["nom"], valeur))
        conn.execute("UPDATE fiche_incomplete SET manque = array_remove(manque, %s) "
                     "WHERE product_id = %s", (champ, product_id))
        ecrites += 1
    conn.execute("DELETE FROM fiche_incomplete WHERE product_id = %s AND cardinality(manque) = 0",
                 (product_id,))
    return ecrites
