"""Deux pieces, une fiche : on separe les fiches qui melangent plusieurs numeros de reference (23/10/2026).

LE CAS. Le kit de vis Lightech 1114850003 (Triumph Street Triple, 73 a 106 EUR) et le kit 1114815003
(Aprilia RS 660, 20 a 55 EUR) etaient sur UNE fiche : le rapprochement lit « Lightech, carenage, vis, or » et
ignore le numero de reference. La regle qui separe les fiches fourre-tout de pieces (`match._SPLIT_PIECES`)
ne joue qu'a partir de trois codes-barres par fiche : ici il n'y en a que deux. Mesure du 23/10 : 282 fiches
ou un MEME marchand donne deux numeros de reference et deux codes-barres (196 en transmission).

LA REGLE. Une fiche est separee si, hors habillement :
  - un meme marchand y porte deux codes-barres dont les titres citent deux numeros de reference differents
    (8 a 12 chiffres) : le marchand lui-meme les vend comme deux articles ;
  - un code-barres n'a de numero que s'il n'en cite qu'UN dans tous ses titres (deux marchands qui le
    nomment differemment : on ne devine pas).
Chaque numero devient une fiche. Le groupe qui porte le plus d'offres reste sur la fiche d'origine ; les codes-barres
sans numero y restent aussi. Le numero est ajoute au nom du modele.

TRACE. `separation_trace` garde, pour chaque offre deplacee, sa fiche d'avant et la fiche creee : `defaire()` relit
cette table. Apres une separation : `mcpipe relier-tailles` puis `mcpipe freshness`.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .db import connect

REFERENCE = re.compile(r"(?<![0-9])[0-9]{8,12}(?![0-9])")
# les rayons ou la taille est un vrai attribut : meme liste que `match._RAYONS_HABILLEMENT`
RAYONS_HABILLEMENT = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 23, 26, 27)

_TRACE = """
CREATE TABLE IF NOT EXISTS separation_trace (
    sep_id            bigint NOT NULL,
    raw_offer_id      bigint NOT NULL,
    ancien_product_id bigint NOT NULL,
    nouveau_product_id bigint NOT NULL,
    reference         text NOT NULL,
    fait_le           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sep_id, raw_offer_id)
)
"""


def references_du_titre(titre: str, gtin: str | None = None) -> set[str]:
    """Les numeros de reference (8 a 12 chiffres) cites dans un titre, hors code-barres."""
    return {t for t in REFERENCE.findall(titre or "") if t != (gtin or "")}


def planifier(offres: list[tuple[int, str, int, str, str]]) -> dict[str, str] | None:
    """Pour UNE fiche : gtin -> numero de reference, ou None s'il n'y a rien a separer.

    `offres` : (id offre, gtin, id marchand, titre, statut) des offres vivantes de la fiche.
    Ne rend un plan que si un meme marchand cite deux numeros sur deux codes-barres, et seuls les codes-barres
    qui n'ont qu'UN numero dans tous leurs titres y figurent.
    """
    par_gtin: dict[str, set[str]] = defaultdict(set)
    par_marchand: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for _, gtin, marchand, titre, _statut in offres:
        if not gtin:
            continue
        refs = references_du_titre(titre, gtin)
        par_gtin[gtin] |= refs
        for r in refs:
            par_marchand[marchand][gtin].add(r)
    preuve = any(
        len({r for refs in g.values() for r in refs}) >= 2 and len(g) >= 2
        and all(len(refs) == 1 for refs in g.values())
        for g in par_marchand.values())
    if not preuve:
        return None
    plan = {g: next(iter(refs)) for g, refs in par_gtin.items() if len(refs) == 1}
    return plan if len(set(plan.values())) >= 2 else None


def _fiches_candidates(cur) -> dict[int, list[tuple[int, str, int, str, str]]]:
    cur.execute(
        """
        SELECT ro.product_id, ro.id, ro.raw_gtin, ro.merchant_id, ro.raw_title, p.slug
        FROM raw_offer ro JOIN product p ON p.id = ro.product_id
        WHERE ro.is_live AND ro.linked_status = 'linked' AND ro.raw_gtin IS NOT NULL AND ro.raw_gtin <> ''
          AND p.status <> 'merged' AND p.category_id <> ALL(%s)
          AND ro.raw_title ~ '(^|[^0-9])[0-9]{8,12}([^0-9]|$)'
        """, (list(RAYONS_HABILLEMENT),))
    par_fiche: dict[int, list] = defaultdict(list)
    for pid, oid, gtin, mid, titre, slug in cur.fetchall():
        par_fiche[pid].append((oid, gtin, mid, titre, slug))
    return par_fiche


def appliquer(ecrire: bool = False) -> dict[str, int]:
    """Calcule les separations ; `ecrire=True` les applique (avec trace)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_TRACE)
            cur.execute("SELECT coalesce(max(sep_id), 0) FROM separation_trace")
            sep_id = cur.fetchone()[0] + 1
            fiches = _fiches_candidates(cur)
            bilan = {"fiches_separees": 0, "fiches_creees": 0, "offres_deplacees": 0}
            for pid, offres in fiches.items():
                plan = planifier([(o[0], o[1], o[2], o[3], o[4]) for o in offres])
                if not plan:
                    continue
                # toutes les offres vivantes ou non de la fiche, pour les codes-barres du plan
                cur.execute("SELECT id, raw_gtin FROM raw_offer WHERE product_id = %s AND raw_gtin = ANY(%s)",
                            (pid, list(plan)))
                par_ref: dict[str, list[tuple[int, str]]] = defaultdict(list)
                for oid, gtin in cur.fetchall():
                    par_ref[plan[gtin]].append((oid, gtin))
                gardee = max(par_ref, key=lambda r: (len(par_ref[r]), r))
                bilan["fiches_separees"] += 1
                cur.execute("SELECT brand_code, category_id, model_core_ref, model_display, colour_code, model_year,"
                            " genre_age, identity_hash, slug FROM product WHERE id = %s", (pid,))
                brand, cat, core, display, colour, year, genre, ihash, slug = cur.fetchone()
                for ref, lignes in par_ref.items():
                    if ref == gardee:
                        continue
                    bilan["fiches_creees"] += 1
                    bilan["offres_deplacees"] += len(lignes)
                    if not ecrire:
                        continue
                    nouveau_hash = "ref-" + ihash[:20] + "|" + ref
                    cur.execute(
                        """
                        INSERT INTO product (brand_code, category_id, model_core_ref, model_display, colour_code,
                                             model_year, genre_age, identity_hash, slug)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, md5(%s),
                                regexp_replace(%s, '-[0-9a-f]{8}$', '') || '-' || %s || '-' || left(md5(%s), 8))
                        ON CONFLICT (identity_hash) DO UPDATE SET identity_hash = product.identity_hash
                        RETURNING id
                        """,
                        (brand, cat, core, f"{display} {ref}", colour, year, genre, nouveau_hash, slug, ref, nouveau_hash))
                    nouveau = cur.fetchone()[0]
                    ids = [oid for oid, _ in lignes]
                    cur.execute("INSERT INTO separation_trace (sep_id, raw_offer_id, ancien_product_id, nouveau_product_id,"
                                " reference) SELECT %s, id, %s, %s, %s FROM raw_offer WHERE id = ANY(%s)"
                                " ON CONFLICT DO NOTHING", (sep_id, pid, nouveau, ref, ids))
                    cur.execute("UPDATE raw_offer SET product_id = %s WHERE id = ANY(%s)", (nouveau, ids))
                    cur.execute("DELETE FROM offer_variant_link WHERE raw_offer_id = ANY(%s)", (ids,))
                if ecrire:
                    cur.execute("UPDATE product SET model_display = model_display || ' ' || %s WHERE id = %s"
                                " AND model_display NOT LIKE '%%' || %s", (gardee, pid, gardee))
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


def defaire(sep_id: int) -> int:
    """Remet les offres d'une separation sur leur fiche d'avant ; les fiches creees passent en `merged`."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE raw_offer o SET product_id = t.ancien_product_id FROM separation_trace t"
                        " WHERE t.sep_id = %s AND o.id = t.raw_offer_id", (sep_id,))
            n = cur.rowcount
            cur.execute("UPDATE product p SET status = 'merged', merged_into = t.ancien_product_id FROM"
                        " (SELECT DISTINCT nouveau_product_id, ancien_product_id FROM separation_trace WHERE sep_id = %s) t"
                        " WHERE p.id = t.nouveau_product_id", (sep_id,))
        conn.commit()
        return n
    finally:
        conn.close()
