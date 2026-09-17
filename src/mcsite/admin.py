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
