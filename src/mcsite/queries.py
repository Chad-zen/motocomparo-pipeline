"""Every SQL statement the site runs, in one file.

Read-only by construction: no INSERT, UPDATE or DELETE appears here. The site
can never corrupt what the pipeline computed.

Two rules these queries follow, both learned from v1:
  * listings read `product_stats`, never the 763k offers directly — counting
    merchants per page view is what made v1 crawl;
  * an offer is shown only if the pipeline linked it AND the feed still lists it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import psycopg
from psycopg.rows import dict_row

# An offer worth showing. Kept as one string so no query can disagree with another.
# 9 999,00 € pile n'est pas un prix : c'est la valeur que FC-Moto met quand son
# flux n'a pas de prix (6 offres le 14/09/2026, toutes des supports SW-Motech).
# Elle faussait 5 courbes d'historique, où le prix semblait passer de 50 € à
# 9 999 €. Écartée à l'affichage ; à traiter dans `normalize` quand le pipeline
# repassera, car c'est là qu'un non-prix devrait devenir NULL.
_PRIX_SENTINELLE = "9999.00"

_SHOWABLE = ("o.linked_status = 'linked' AND o.is_live AND o.product_id IS NOT NULL"
             f" AND (o.price IS NULL OR o.price <> {_PRIX_SENTINELLE})")

# Category 25 is the pipeline's "not classified yet" sentinel, not a department.
# It must never appear in navigation: a visitor cannot browse a fourre-tout.
UNCLASSIFIED_ID = 25


def _rows(conn: psycopg.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def _row(conn: psycopg.Connection, sql: str, args: tuple = ()) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchone()


# --------------------------------------------------------------------------- home

def categories(conn: psycopg.Connection, min_merchants: int = 2) -> list[dict[str, Any]]:
    """Browsing, as a tree: parents first, each carrying its children.

    `category` has a `parent_id` — helmets split into integral, jet, modular and
    cross — and flattening it put "Casques 79" beside "Casques intégraux 1,267",
    which reads as a bug. 79 is only the helmets no subtype could be read from;
    the department really holds 2,708.

    A parent's `n` therefore counts its children too, and `ids` lists every
    category a click on it should search. Children keep their own counts.
    """
    lignes = _rows(conn, """
        SELECT c.id, c.parent_id, c.code, c.label_fr,
               count(*) FILTER (WHERE s.merchant_count >= %s
                                AND s.cheapest IS NOT NULL
                                AND p.status <> 'merged') AS n,
               min(s.cheapest) FILTER (WHERE s.merchant_count >= %s) AS from_price,
               -- one real product photo per department, for the tiles and the
               -- drawer. Dafy has no drawn category icons at all and Motoblouz
               -- uses a product shot for its home tiles: a photo of the thing
               -- says "helmet" better than any 24px drawing of one, and this
               -- catalogue already carries 400k of them.
               (array_agg(s.image_url ORDER BY s.merchant_count DESC, s.cheapest)
                FILTER (WHERE s.image_url IS NOT NULL AND s.image_url <> ''
                          AND s.merchant_count >= %s))[1] AS image_url
        FROM category c
        LEFT JOIN product p ON p.category_id = c.id
        LEFT JOIN product_stats s ON s.product_id = p.id
        WHERE c.id <> 25
        GROUP BY c.id, c.parent_id, c.code, c.label_fr
    """, (min_merchants, min_merchants, min_merchants))

    par_id = {r["id"]: r for r in lignes}
    for r in lignes:
        r["enfants"] = []
        r["ids"] = [r["id"]]

    racines: list[dict[str, Any]] = []
    for r in lignes:
        parent = par_id.get(r["parent_id"]) if r["parent_id"] else None
        if parent is not None:
            parent["enfants"].append(r)
        else:
            racines.append(r)

    for r in racines:
        r["enfants"].sort(key=lambda e: -e["n"])
        r["ids"] += [e["id"] for e in r["enfants"]]
        r["n"] += sum(e["n"] for e in r["enfants"])
        prix = [e["from_price"] for e in r["enfants"] if e["from_price"] is not None]
        if r["from_price"] is None and prix:
            r["from_price"] = min(prix)
        # A parent's own bucket is the RESIDUE — "Casques" holds only the helmets
        # no subtype could be read from — so its photo comes out of a thin and
        # unrepresentative pool: it drew a sun-visor kit. The largest child is
        # the department's real face, so it always wins when there is one.
        enfant = next((e["image_url"] for e in r["enfants"] if e["image_url"]), None)
        if enfant:
            r["image_url"] = enfant

    # L'ORDRE N'EST PLUS CELUI DU NOMBRE DE FICHES, et c'est une décision
    # éditoriale de la propriétaire (18/09/2026).
    #
    # Classés par taille, les trois premiers rayons étaient Bagagerie, Blousons
    # et Casques : le catalogue le plus gros passait devant, pas le besoin le
    # plus courant. Or personne n'arrive sur un comparateur d'équipement moto
    # en cherchant d'abord un top-case. On vient pour un casque.
    #
    # Casque, blouson, gants ouvrent donc la marche — c'est aussi l'ordre dans
    # lequel un motard s'équipe, et celui des trois pièces qu'on ne peut pas ne
    # pas avoir. Le reste suit au nombre de fiches, qui reste le bon critère
    # quand aucune raison éditoriale ne tranche.
    TETE = ["helmet", "jacket", "gloves"]
    return sorted(
        [r for r in racines if r["n"] > 0],
        # `len(TETE)` pour les autres : ils gardent leur rang relatif, réglé par
        # le second critère. Un rayon absent de TETE ne doit pas remonter.
        key=lambda r: (TETE.index(r["code"]) if r["code"] in TETE else len(TETE),
                       -r["n"]))


def find_category(cats: list[dict[str, Any]], code: str) -> dict[str, Any] | None:
    """Locate a category by code anywhere in the tree, parent or child."""
    for c in cats:
        if c["code"] == code:
            return c
        for e in c["enfants"]:
            if e["code"] == code:
                return e
    return None


def totals(conn: psycopg.Connection) -> dict[str, Any]:
    row = _row(conn, """
        SELECT count(*) AS products,
               count(*) FILTER (WHERE merchant_count >= 2) AS comparable,
               sum(offer_count) AS offers
        FROM product_stats
    """)
    return row or {}


# ------------------------------------------------------------------------ listing

def listing(
    conn: psycopg.Connection,
    category_ids: list[int] | None,
    min_merchants: int,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """One page of products.

    The window is taken FIRST, then the per-product extras are looked up for the
    24 rows that survived — not for the whole catalogue.
    """
    return _rows(conn, """
        SELECT p.slug, p.brand_code, p.model_display, p.colour_code,
               s.cheapest, s.dearest, s.merchant_count, s.image_url, s.best_title,
               c.label_fr AS category_label
        FROM product p
        JOIN product_stats s ON s.product_id = p.id
        JOIN category c ON c.id = p.category_id
        WHERE (%s::smallint[] IS NULL OR p.category_id = ANY(%s::smallint[]))
          AND s.merchant_count >= %s
          AND s.cheapest IS NOT NULL
          AND p.status <> 'merged'
        ORDER BY s.merchant_count DESC, s.cheapest
        LIMIT %s OFFSET %s
    """, (category_ids, category_ids, min_merchants, limit, offset))


def rayons(
    conn: psycopg.Connection, familles: list[dict[str, Any]], par_rayon: int = 10
) -> list[dict[str, Any]]:
    """One shelf per top-level category, each with its best products.

    The v1 home page is a stack of shelves — "Casques", "Blousons", "Gants" —
    rather than one undifferentiated grid, and that is the whole reason the page
    reads as a shop. Reproducing it needs the top N of each family.

    One query, not one per family: nine round trips on the home page would be
    nine chances for the slowest of them to set the page's speed. `ROW_NUMBER`
    ranks inside each family and the outer filter keeps the head of each.

    Ordered by merchant count first: a shelf exists to show the comparison, so
    the product compared by the most merchants leads it.
    """
    if not familles:
        return []
    # one row per (family, category id): PostgreSQL's `unnest` flattens a 2-D
    # array, so a list of lists cannot be passed as one column — the pairs are
    # flattened here instead, where it is plain to read.
    couples = [(f["code"], cid) for f in familles for cid in f["ids"]]
    rows = _rows(conn, """
        WITH famille AS (
            SELECT unnest(%s::text[]) AS code, unnest(%s::smallint[]) AS category_id
        ),
        classe AS (
            SELECT f.code AS famille, p.slug, p.brand_code, p.model_display,
                   p.colour_code, s.cheapest, s.dearest, s.merchant_count,
                   s.image_url, s.best_title,
                   row_number() OVER (PARTITION BY f.code
                                      ORDER BY s.merchant_count DESC, s.cheapest) AS rang
            FROM famille f
            JOIN product p ON p.category_id = f.category_id
            JOIN product_stats s ON s.product_id = p.id
            WHERE s.merchant_count >= 2 AND s.cheapest IS NOT NULL
              AND p.status <> 'merged'
        )
        SELECT * FROM classe WHERE rang <= %s
    """, ([c for c, _ in couples], [i for _, i in couples], par_rayon))

    par_famille: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        par_famille.setdefault(r["famille"], []).append(r)
    return [
        {**f, "items": par_famille[f["code"]]}
        for f in familles if par_famille.get(f["code"])
    ]


def ecarts(conn: psycopg.Connection, limit: int = 12,
           jour: str | None = None,
           min_marchands: int = 3) -> list[dict[str, Any]]:
    """Where choosing the right merchant saves the most.

    A price comparison site's equivalent of a deals row — and the honest one.
    idealo shows "-18 %" against a reference price nobody verifies; here the
    percentage is the gap between the cheapest and the dearest merchant for the
    SAME article, today. Nothing is claimed about what it used to cost.

    ⚠️ Cette rangée lit `product_stats`, dont `cheapest` et `dearest` sont un
    simple min/max sur toutes les offres de la fiche : les deux prix peuvent
    donc venir du MÊME marchand, ou de deux tailles différentes. La page
    `/bons-plans` a été refaite pour comparer au niveau du code-barres ; celle-ci
    ne l'est pas encore, et le libellé a été corrigé en conséquence — il dit
    « d'écart sur cette fiche » et non plus « entre marchands ».

    Capped at a factor of two on purpose. A product whose offers differ by more
    than that is far more often a bad merge than a bargain — `ops/mesure_catalogue.py`
    tracks exactly that shape as a defect (`fusion_ecart_prix_x10`). Leading the
    home page with our own worst merges would advertise the bug.
    """
    jour = jour or date.today().isoformat()
    return _rows(conn, """
        WITH candidat AS (
            -- one line per model, not per colourway: the same GPR silencer in
            -- three finishes is three products and would fill the row on its own
            SELECT DISTINCT ON (p.brand_code, p.model_display)
                   p.slug, p.brand_code, p.model_display, p.colour_code,
                   s.cheapest, s.dearest, s.merchant_count, s.image_url,
                   s.best_title,
                   round((1 - s.cheapest / s.dearest) * 100) AS remise
            FROM product p
            JOIN product_stats s ON s.product_id = p.id
            -- TROIS marchands, pas deux. Règle de la propriétaire, 17/09/2026 :
            -- « je ne veux aucune offre à moins de 3 marchands dans la home
            -- page ». Sur un comparateur c'est cohérent — une fiche à deux
            -- offres montre un écart, trois montrent un marché. Mesuré : 5 777
            -- candidats à deux marchands, 2 389 à trois, de quoi remplir
            -- largement une rangée de douze.
            WHERE s.merchant_count >= %s AND p.status <> 'merged'
              -- Pas de photo, pas de place sur l'accueil. Regle de la
              -- proprietaire, 18/09/2026 : une carte « pas de visuel » posee au
              -- milieu de onze photos ne se lit pas comme une fiche sans image,
              -- elle se lit comme un site casse.
              --
              -- Aucune fiche n'est dans ce cas aujourd'hui : 0 sur 8 221 a
              -- trois marchands. La garde ne sert donc a rien maintenant, et
              -- c'est exactement pourquoi elle est ecrite — le jour ou un
              -- marchand retirera une photo, personne ne relancera la mesure.
              AND s.image_url IS NOT NULL AND s.image_url <> ''
              AND s.cheapest IS NOT NULL AND s.dearest IS NOT NULL
              AND s.cheapest > 0
              AND s.dearest <= s.cheapest * 2      -- au-delà : un défaut, pas une affaire
              AND s.dearest >= s.cheapest * 1.15   -- en-deçà : pas la peine de le montrer
              -- et l'écart doit peser en euros : la moitie du prix d'une
              -- chambre a air fait 7 EUR, et une rangee de piecettes ne donne a
              -- personne l'envie de comparer
              AND s.dearest - s.cheapest >= 25
            -- `p.slug` clôt le tri. Le défaut est ancien : à écart égal, deux
            -- coloris sortaient dans un ordre libre. Il ne se voyait pas tant
            -- que la rangée classait au pourcentage ; il éclate dès qu'un
            -- hachage du slug entre dans le tri, puisque le slug retenu
            -- changeait d'une visite à l'autre.
            ORDER BY p.brand_code, p.model_display, (s.dearest - s.cheapest) DESC,
                     p.slug
        )
        ,
        -- La rangée ne montre PLUS les douze plus gros pourcentages. Triée
        -- ainsi, elle affichait douze fois la même chose : les extrêmes du
        -- catalogue, c'est-à-dire ses articles les plus chers et ses fusions
        -- les plus douteuses. Un visiteur n'y apprenait rien du reste.
        --
        -- Les écarts sont donc rangés par TRANCHE de dix points, et la rangée
        -- se sert dans chacune à tour de rôle : une affaire à 18 points, une à
        -- 28, une à 40, puis on recommence. C'est la consigne de la
        -- propriétaire — « pas celles qui sont le plus élevées, varie les
        -- baisses » — et c'est aussi la rangée la plus honnête, parce qu'elle
        -- décrit la distribution au lieu de n'en montrer que la queue.
        -- La bande 0 est écartée : elle tenait le seuil d'`1.15` sur les prix,
        -- qui arrondi tombe à −13, et la rangée s'ouvrait donc sur « −14 ».
        -- La consigne dit « réductions IMPORTANTES, mais variées » : varier ne
        -- veut pas dire descendre.
        tranche AS (
            SELECT *, width_bucket(remise, 15, 55, 4) AS bande FROM candidat
        ),
        -- une seule fiche par marque DANS une tranche : sans cela, une marque
        -- au catalogue large prend la bande entière.
        unique_marque AS (
            SELECT *, row_number() OVER (PARTITION BY bande, brand_code
                                         ORDER BY hashtext(slug || %s)) AS r_marque
            FROM tranche WHERE bande >= 1
        ),
        -- `hashtext(slug || le jour)` : un ordre arbitraire mais STABLE sur la
        -- journée. Un `random()` changerait à chaque calcul — donc à chaque
        -- expiration du cache — et la rangée sauterait sous les yeux du
        -- visiteur qui revient ; figée pour toujours, elle ne montrerait jamais
        -- que les mêmes douze fiches. Elle tourne une fois par jour.
        choix AS (
            SELECT *, row_number() OVER (PARTITION BY bande
                                         ORDER BY hashtext(slug || %s)) AS rang
            FROM unique_marque WHERE r_marque = 1
        )
        SELECT * FROM choix ORDER BY rang, bande LIMIT %s
    """, (min_marchands, jour, jour, limit))


def nouveautes(conn: psycopg.Connection, ids: list[int],
               limit: int = 12,
               min_marchands: int = 3) -> list[dict[str, Any]]:
    """Ce qui vient d'entrer au catalogue, dans un rayon donné.

    ATTENTION À LA DATE QU'ON LIT. `product.created_at` vaut 2026-09-14 pour les
    313 435 fiches : c'est le jour où la table a été reconstruite, pas une date
    de nouveauté. S'en servir aurait donné une rangée « Nouveautés » tirée au
    hasard dans tout le catalogue — un mensonge sans même le savoir.

    La vraie date d'arrivée est celle de la première offre vue, `first_seen`.
    Encore faut-il écarter le versement initial, qui a fait naître 763 570
    offres le même jour : est nouveau ce qui est apparu APRÈS ce jour-là. Le
    seuil n'est pas écrit en dur, il se lit — le `min(first_seen)` de la table —
    pour qu'une base repartie de zéro n'ait rien à corriger ici.

    La rangée est donc courte au début (37 casques le 17/09) et grandit d'un
    jour sur l'autre. C'est le comportement voulu : mieux vaut une rangée courte
    et vraie qu'une rangée pleine et inventée.
    """
    if not ids:
        return []
    return _rows(conn, """
        WITH chargement AS (
            -- le jour du versement initial, lu et non supposé
            SELECT min(first_seen)::date AS jour FROM raw_offer
        ),
        -- On part du PETIT ensemble : les 10 187 offres arrivées après ce
        -- jour-là, pas les 763 570 de la table. L'écrire dans l'autre sens —
        -- un `min(first_seen) GROUP BY product_id` sur tout — coûtait 5,1 s
        -- pour le même résultat, parce qu'il calculait la date d'arrivée de
        -- chaque fiche du catalogue avant d'en jeter 99 pour cent.
        candidate AS (
            SELECT DISTINCT o.product_id
            FROM raw_offer o, chargement c
            WHERE o.first_seen >= (c.jour + 1)::timestamptz
              AND o.product_id IS NOT NULL AND o.linked_status = 'linked'
        ),
        -- Puis on vérifie que la fiche n'existait PAS avant : une offre neuve
        -- sur une fiche ancienne, c'est un marchand de plus, pas une nouveauté.
        neuve AS (
            SELECT k.product_id,
                   (SELECT min(o2.first_seen)::date FROM raw_offer o2
                    WHERE o2.product_id = k.product_id) AS vue_le
            FROM candidate k
        ),
        modele AS (
            -- un coloris par modèle, pas trois fois le même casque
            -- `p.slug` clôt le tri : sans lui, deux fiches à égalité sortaient
            -- dans un ordre libre et la rangée changeait d'une visite à l'autre
            -- sans qu'aucune donnée n'ait bougé.
            SELECT DISTINCT ON (p.brand_code, p.model_display)
                   p.slug, p.brand_code, p.model_display, p.colour_code,
                   s.cheapest, s.dearest, s.merchant_count, s.image_url,
                   s.best_title, n.vue_le
            FROM neuve n
            JOIN chargement c ON n.vue_le > c.jour
            JOIN product p ON p.id = n.product_id
            JOIN product_stats s ON s.product_id = p.id
            WHERE p.category_id = ANY(%s) AND p.status <> 'merged'
              AND s.cheapest IS NOT NULL
              -- Même règle que partout sur l'accueil. ⚠️ Elle vide CETTE
              -- rangée : une fiche qui vient d'arriver est chez UN marchand par
              -- construction, et il faut des semaines pour que trois la
              -- listent. Mesuré le 17/09/2026 : 40 nouveautés casque à un
              -- marchand ou plus, ZÉRO à trois. La rangée ne s'affiche donc
              -- pas du tout : le gabarit ne rend la section que si la rangée
              -- contient quelque chose. Mieux vaut une rangée absente qu'une
              -- montrer une règle enfreinte.
              AND s.merchant_count >= %s
              AND s.image_url IS NOT NULL AND s.image_url <> ''
            ORDER BY p.brand_code, p.model_display, n.vue_le DESC,
                     s.merchant_count DESC, p.slug
        ),
        -- puis le tour de rôle par marque : sur 37 candidats, le classement
        -- par date donnait quatre Airoh sur douze. Une rangée « Nouveautés »
        -- sert à montrer ce qui est arrivé, pas qui a le plus gros catalogue.
        tour_de_role AS (
            SELECT *, row_number() OVER (PARTITION BY brand_code
                                         ORDER BY vue_le DESC, slug) AS rang
            FROM modele
        )
        SELECT * FROM tour_de_role ORDER BY rang, vue_le DESC, slug
    """, (ids, min_marchands))[:limit]


def baisses(conn: psycopg.Connection, limit: int = 12,
            jours: int = 7, par_marchand: int = 3,
            min_marchands: int = 3) -> list[dict[str, Any]]:
    """Ce qui a réellement baissé : la MÊME offre, comparée à elle-même.

    LA COMPARAISON QU'IL NE FAUT PAS FAIRE : le prix mini d'il y a une semaine
    contre le prix mini d'aujourd'hui. Ces deux minimums ne portent pas sur la
    même population — un marchand moins cher qui ARRIVE ferait baisser le
    second sans qu'aucun prix n'ait bougé, et la rangée annoncerait une baisse
    qui n'a pas eu lieu. On compare donc une offre à elle-même, par son
    identifiant, et seulement celle qui porte le prix affiché aujourd'hui : ce
    qui a baissé, c'est bien ce que le visiteur lit en tête de fiche.

    CE QUE LES DONNÉES DISENT (mesuré le 17/09 sur la fenêtre 12→14). Les
    baisses se massent sur des rapports ronds — 0,90, 0,85, 0,80, 0,70 — ce sont
    des opérations commerciales, pas du bruit. Mais elles sont très inégalement
    réparties : FC-Moto a baissé 112 149 de ses 143 523 offres, La Bécanerie
    n'en a bougé aucune sur 222 907. Classée au pourcentage, la rangée aurait
    donc montré douze articles FC-Moto à −30 % — la promotion d'un marchand,
    présentée comme l'actualité du catalogue.

    D'où le tour de rôle : le meilleur de chaque marchand d'abord, puis le
    deuxième de chacun. Avec six marchands et douze cases, aucun n'en prend plus
    de deux.

    La fenêtre est de sept jours, mais elle part du premier relevé qu'elle y
    trouve : l'historique n'a que quatre jours (12, 13, 14 et 17 septembre, les
    15 et 16 n'ayant rien collecté). La rangée est juste sur ce qu'elle mesure,
    et s'étendra d'elle-même à mesure que les relevés s'accumulent.
    """
    return _rows(conn, """
        WITH borne AS (
            SELECT min(observed_on) AS debut FROM price_history
            WHERE observed_on >= current_date - %s
        ),
        depart AS (
            SELECT h.raw_offer_id, h.price AS avant
            FROM price_history h JOIN borne b ON h.observed_on = b.debut
            WHERE h.price > 0
        ),
        -- Les offres qui ont bougé, AVANT de regarder les fiches. C'est
        -- l'ordre qui compte : chercher d'abord l'offre la moins chère de
        -- chacune des 313 435 fiches, puis jeter celles qui n'ont pas bougé,
        -- coûtait 7,2 s. Ici le filtre sur le prix tombe en premier et ne
        -- laisse passer qu'une poignée de milliers de lignes.
        chute AS (
            SELECT o.id AS offre_id, o.product_id, o.price AS maintenant,
                   o.merchant_id, d.avant,
                   round((1 - o.price / d.avant) * 100) AS baisse
            FROM depart d JOIN raw_offer o ON o.id = d.raw_offer_id
            WHERE o.is_live AND o.linked_status = 'linked'
              AND o.product_id IS NOT NULL AND o.price IS NOT NULL
              AND o.in_stock IS NOT FALSE AND o.price > 0
              AND o.price <= d.avant * 0.9     -- en-deçà : pas une nouvelle
              -- Une limite haute qui ATTIRE au lieu d'écarter ne sert à rien :
              -- posée aux sept dixièmes, elle remplissait la rangée de FC-Moto
              -- à −70 pile, toutes ses opérations venant buter dessus. Ramenée
              -- à un peu plus de la moitié, elle redevient ce qu'elle doit
              -- être — une garde contre l'erreur de flux, pas un tri.
              AND o.price >= d.avant * 0.45
              -- et la baisse doit peser en euros : un écran de casque qui
              -- passe de 15,00 € à 4,53 € affiche un beau pourcentage et ne
              -- mérite pas la page d'accueil.
              AND d.avant - o.price >= 20
        ),
        -- l'offre qui a baissé doit être celle qui FAIT le prix affiché :
        -- sinon la rangée annonce une baisse que la fiche ne montre pas.
        mouvement AS (
            SELECT c.* FROM chute c
            WHERE NOT EXISTS (
                SELECT 1 FROM raw_offer a
                WHERE a.product_id = c.product_id AND a.linked_status = 'linked'
                  AND a.price IS NOT NULL AND a.price < c.maintenant
                  AND a.is_live AND a.in_stock IS NOT FALSE
            )
        ),
        -- une seule fiche par marque, la plus forte baisse
        unique_marque AS (
            SELECT DISTINCT ON (p.brand_code)
                   p.slug, p.brand_code, p.model_display, p.colour_code,
                   s.cheapest, s.dearest, s.merchant_count, s.image_url,
                   s.best_title, m.avant, m.maintenant, m.baisse, m.merchant_id
            FROM mouvement m
            JOIN product p ON p.id = m.product_id
            JOIN product_stats s ON s.product_id = p.id
            WHERE p.status <> 'merged' AND s.cheapest IS NOT NULL
              AND s.merchant_count >= %s        -- même règle que `ecarts`
              AND s.image_url IS NOT NULL AND s.image_url <> ''
            -- `p.slug` PUIS `m.merchant_id` closent le tri, et il faut les
            -- deux. Le slug seul ne suffisait pas : quand DEUX marchands
            -- affichent le même prix sur la même fiche — le Shark OXO Rydger
            -- chez Maxxess et Moto-Axxe — les deux lignes sont identiques
            -- jusqu'au slug, et PostgreSQL en gardait une au hasard. La fiche
            -- ne changeait pas, mais le marchand retenu si — et comme le tour
            -- de rôle plus bas répartit PAR marchand, toute la rangée se
            -- réorganisait derrière. Un ex æquo sur un seul champ suffit à
            -- rendre douze cartes instables.
            ORDER BY p.brand_code, m.baisse DESC, p.slug, m.merchant_id
        ),
        tour_de_role AS (
            SELECT *, row_number() OVER (PARTITION BY merchant_id
                                         -- `slug` clôt le tri : deux baisses
                                         -- égales chez le même marchand se
                                         -- classaient dans un ordre libre, et
                                         -- la rangée changeait d'un calcul à
                                         -- l'autre sans qu'aucune donnée n'ait
                                         -- bougé. Les baisses se massent sur
                                         -- des rapports ronds — 0,90, 0,85,
                                         -- 0,70 — donc les ex æquo sont la
                                         -- règle ici, pas l'exception.
                                         ORDER BY baisse DESC, slug) AS rang
            FROM unique_marque
        )
        -- Le tour de rôle ne suffisait pas : quand les autres marchands sont à
        -- court de candidats, la queue de la rangée se remplit du seul qui en a
        -- encore — six places sur douze pour FC-Moto, toutes à −55 pile. Le
        -- plafond est donc dur. La rangée a le droit d'être plus courte que
        -- douze ; elle n'a pas le droit d'être le catalogue d'un marchand.
        SELECT * FROM tour_de_role WHERE rang <= %s
        ORDER BY rang, baisse DESC, slug
        LIMIT %s
    """, (jours, min_marchands, par_marchand, limit))


def par_slugs(conn: psycopg.Connection, slugs: list[str]) -> list[dict[str, Any]]:
    """The products the visitor put aside, in the order they put them there.

    Kept in the browser, not on the server: the site has no accounts and asks for
    no e-mail address, so a shortlist cannot live anywhere else. The page
    receives the list in its own URL — which also makes it shareable, and lets
    the server render the cards exactly as everywhere else instead of a second
    rendering path in JavaScript.
    """
    if not slugs:
        return []
    lignes = _rows(conn, """
        SELECT p.id AS product_id, p.slug, p.brand_code, p.model_display, p.colour_code,
               p.category_id, s.cheapest, s.dearest, s.merchant_count, s.image_url, s.best_title,
               c.code AS category_code, c.label_fr AS category_label
        FROM product p
        JOIN product_stats s ON s.product_id = p.id
        JOIN category c ON c.id = p.category_id
        WHERE p.slug = ANY(%s)
    """, (slugs[:40],))
    rang = {s_: i for i, s_ in enumerate(slugs)}
    return sorted(lignes, key=lambda r: rang.get(r["slug"], 999))


def affiche(conn: psycopg.Connection) -> dict[str, Any] | None:
    """The one product the home banner is built around.

    A banner that names a real article, at today's real prices, says more than
    any slogan — and it cannot go stale, because it is recomputed on every
    visit. Helmets lead it: it is the department visitors come for, and the one
    where merchants disagree most on price.

    Same two guards as `ecarts()`, for the same reasons: above a factor of two a
    gap is almost always a bad merge rather than a bargain, and three merchants
    rather than two make the claim harder to dismiss.
    """
    lignes = _rows(conn, """
        SELECT p.slug, p.brand_code, s.best_title, s.image_url,
               s.cheapest, s.dearest, s.merchant_count,
               s.dearest - s.cheapest AS economie,
               round((1 - s.cheapest / s.dearest) * 100) AS remise
        FROM product p
        JOIN product_stats s ON s.product_id = p.id
        JOIN category c ON c.id = p.category_id
        WHERE c.code LIKE 'helmet%%' AND p.status <> 'merged'
          AND s.image_url IS NOT NULL AND s.image_url <> ''
          AND s.merchant_count >= 3
          AND s.cheapest > 0
          AND s.dearest >= s.cheapest * 1.15
          AND s.dearest <= s.cheapest * 2
        ORDER BY (s.dearest - s.cheapest) DESC
        LIMIT 1
    """)
    return lignes[0] if lignes else None


def vitrine(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Five real articles for the banner — one per department, the most compared.

    The banner shows a helmet, a jacket, gloves, boots and an intercom because
    that is what the site is about, and each one is a product actually listed
    here at a price relevés today. A stock illustration would show equipment
    nobody can click on.
    """
    return _rows(conn, """
        SELECT DISTINCT ON (racine.code)
               racine.code AS rayon, p.slug, s.best_title, s.image_url,
               s.cheapest, s.merchant_count
        FROM product p
        JOIN product_stats s ON s.product_id = p.id
        JOIN category c ON c.id = p.category_id
        JOIN category racine ON racine.id = coalesce(c.parent_id, c.id)
        WHERE racine.code IN ('helmet', 'jacket', 'gloves', 'boots', 'electronics')
          AND p.status <> 'merged'
          AND s.image_url IS NOT NULL AND s.image_url <> ''
          AND s.merchant_count >= 2 AND s.cheapest IS NOT NULL
        ORDER BY racine.code, s.merchant_count DESC, s.cheapest DESC
    """)


def similaires(
    conn: psycopg.Connection, produit: dict[str, Any], limit: int = 6
) -> list[dict[str, Any]]:
    """Products a visitor looking at this one would plausibly consider.

    Same three criteria as the v1, and in that order of weight: **the brand**
    first (someone reading an Arai is reading Arai), then **the price bracket**
    — an 80 EUR helmet next to a 1 500 EUR one is not a suggestion, it is noise
    — and finally **how many merchants follow the reference**, because a product
    nobody else sells has nothing to compare and belongs on no shelf here.

    The same department is required, never just the brand: Arai also makes
    visors, and proposing a visor under a helmet reads as a mistake.
    """
    return _rows(conn, """
        WITH candidat AS (
            -- une ligne par MODÈLE, pas par coloris : le même casque cross en
            -- deux couleurs occupait deux cases côte à côte, ce qui se lit comme
            -- un défaut et gâche deux des six places
            SELECT DISTINCT ON (p.brand_code, p.model_display)
                   p.slug, p.brand_code, p.model_display, p.colour_code,
                   s.cheapest, s.merchant_count, s.image_url, s.best_title
            FROM product p
            JOIN product_stats s ON s.product_id = p.id
            JOIN category c ON c.id = p.category_id
            WHERE p.id <> %(id)s
              AND p.status <> 'merged'
              AND s.merchant_count >= 2 AND s.cheapest IS NOT NULL
              AND s.image_url IS NOT NULL AND s.image_url <> ''
              AND coalesce(c.parent_id, c.id) = %(famille)s
            ORDER BY p.brand_code, p.model_display, s.merchant_count DESC, s.cheapest
        )
        SELECT * FROM candidat
        ORDER BY
          (brand_code IS DISTINCT FROM %(marque)s),               -- la marque d'abord
          abs(cheapest - %(prix)s::numeric) / %(prix)s::numeric,  -- puis l'écart de prix
          merchant_count DESC
        LIMIT %(lim)s
    """, {
        "id": produit["id"], "marque": produit["brand_code"],
        "prix": produit["cheapest"] or 1, "famille": produit["famille_id"],
        "lim": limit,
    })


def meme_gamme(
    conn: psycopg.Connection, produit: dict[str, Any], limit: int = 8
) -> list[dict[str, Any]]:
    """Products in the same price bracket — but from OTHER brands.

    That "other brands" is the whole point, and what separates this shelf from
    the one above it. `similaires()` answers "more of the same maker" ; this one
    answers the question a buyer actually has at this moment: *for this budget,
    what else exists?* Keeping the same brand here would print the same six
    products twice.

    Rien du tout sur une fiche NON CLASSÉE : « la même typologie » n'a pas de
    sens quand le produit lui-même n'a pas de rayon. Mesuré sur 300 fiches, ce
    cas sortait une batterie, un lève-moto et un sac de 30 L côte à côte — au
    bon prix, et sans le moindre rapport. Mieux vaut une étagère absente qu'une
    étagère qui décrédibilise la page.
    """
    if produit.get("category_id") == UNCLASSIFIED_ID:
        return []
    return _rows(conn, """
        WITH candidat AS (
            SELECT DISTINCT ON (p.brand_code, p.model_display)
                   p.slug, p.brand_code, p.model_display, p.colour_code,
                   s.cheapest, s.merchant_count, s.image_url, s.best_title
            FROM product p
            JOIN product_stats s ON s.product_id = p.id
            JOIN category c ON c.id = p.category_id
            WHERE p.id <> %(id)s
              AND p.status <> 'merged'
              AND p.brand_code IS DISTINCT FROM %(marque)s
              AND s.merchant_count >= 2 AND s.cheapest IS NOT NULL
              AND s.image_url IS NOT NULL AND s.image_url <> ''
              -- Le RAYON EXACT, pas la famille. Filtrer sur la famille mettait
              -- un pare-carter SW-Motech et une protection moteur R&G en face
              -- d'une protection cervicale Alpinestars : meme prix, meme
              -- famille « Protections », produits sans rapport. Signale par la
              -- proprietaire le 14/09/2026. Une alternative, c'est le meme
              -- objet chez quelqu'un d'autre — pas n'importe quoi au meme prix.
              AND p.category_id = %(rayon)s
              -- une "gamme de prix", c'est plus ou moins un quart du prix :
              -- au-dela on ne propose plus une alternative, on change de budget
              -- (pas de signe pourcent ici : psycopg le lit comme un parametre)
              AND s.cheapest BETWEEN %(prix)s::numeric * 0.75 AND %(prix)s::numeric * 1.25
            ORDER BY p.brand_code, p.model_display, s.merchant_count DESC, s.cheapest
        )
        SELECT * FROM candidat
        ORDER BY abs(cheapest - %(prix)s::numeric), merchant_count DESC
        LIMIT %(lim)s
    """, {"id": produit["id"], "marque": produit["brand_code"],
          "prix": produit["cheapest"] or 1, "rayon": produit["category_id"],
          "lim": limit})


def codes_promo(conn: psycopg.Connection, marchands: list[str]) -> list[dict[str, Any]]:
    """Live promo codes, for the merchants present on this page only.

    Showing a code for a merchant who does not sell this product would send the
    visitor somewhere the product is not. The list is therefore built from the
    offers actually displayed.

    `fin_le >= current_date` is not a convenience: an expired code shown is
    worse than no code at all — the visitor clicks, the code is refused at
    checkout, and they do not come back. The date is required at entry, so a
    forgotten code disappears on its own.
    """
    if not marchands:
        return []
    return _rows(conn, """
        SELECT m.code AS merchant, c.code, c.libelle, c.url, c.fin_le,
               c.conditions, c.source
        FROM code_promo c
        JOIN merchant m ON m.id = c.merchant_id
        WHERE m.code = ANY(%s)
          AND c.retire_le IS NULL
          AND c.debut_le <= current_date
          AND c.fin_le >= current_date
        ORDER BY m.code, c.fin_le
    """, (marchands,))


def listing_count(
    conn: psycopg.Connection, category_ids: list[int] | None, min_merchants: int
) -> int:
    row = _row(conn, """
        SELECT count(*) AS n
        FROM product p JOIN product_stats s ON s.product_id = p.id
        WHERE (%s::smallint[] IS NULL OR p.category_id = ANY(%s::smallint[]))
          AND s.merchant_count >= %s AND s.cheapest IS NOT NULL AND p.status <> 'merged'
    """, (category_ids, category_ids, min_merchants))
    return int(row["n"]) if row else 0


# ------------------------------------------------------------------------ product

def product(conn: psycopg.Connection, slug: str) -> dict[str, Any] | None:
    return _row(conn, """
        SELECT p.id, p.brand_code, p.model_display, p.colour_code, p.genre_age,
               p.model_year, p.min_price, p.status, p.slug,
               c.id AS category_id, c.code AS category_code, c.label_fr AS category_label,
               coalesce(c.parent_id, c.id) AS famille_id,
               s.merchant_count, s.offer_count, s.cheapest, s.dearest, s.image_url,
               s.best_title
        FROM product p
        JOIN category c ON c.id = p.category_id
        LEFT JOIN product_stats s ON s.product_id = p.id
        WHERE p.slug = %s
    """, (slug,))


def offers(conn: psycopg.Connection, product_id: int) -> list[dict[str, Any]]:
    """The comparison itself, one row per merchant offer, with its size.

    Sorting happens on the page, because the visitor filters by size and the
    cheapest offer changes with the filter.

    Out-of-stock offers are kept — the owner's rule is that nothing disappears,
    it is marked. `in_stock IS NULL` means the merchant said nothing, which is
    not the same as "out of stock" and must not be displayed as one.
    """
    return _rows(conn, f"""
        SELECT DISTINCT ON (o.id)
               m.code AS merchant, o.id AS offer_id, o.price, o.currency, o.in_stock,
               o.gtin,
               o.deeplink, o.raw_title, o.image_url, o.last_seen,
               coalesce(v.size_code, o.raw_size) AS size_code,
               o.last_seen >= now() - interval '24 hours' AS fresh
        FROM raw_offer o
        -- `m.affiche` : un marchand mis de côté disparaît aussi de la FICHE, pas
        -- seulement des agrégats. Sans cette ligne, `product_stats` aurait
        -- annoncé « 2 marchands comparés » pendant que le tableau en listait
        -- trois — une incohérence visible du visiteur et muette pour nous.
        JOIN merchant m ON m.id = o.merchant_id AND m.affiche
        LEFT JOIN offer_variant_link l ON l.raw_offer_id = o.id
        LEFT JOIN variant v ON v.id = l.variant_id
        WHERE o.product_id = %s AND {_SHOWABLE}
        ORDER BY o.id, v.size_code
    """, (product_id,))


def sizes(conn: psycopg.Connection, product_id: int) -> list[str]:
    rows = _rows(conn, f"""
        SELECT DISTINCT v.size_code
        FROM variant v
        JOIN offer_variant_link l ON l.variant_id = v.id
        JOIN raw_offer o ON o.id = l.raw_offer_id AND {_SHOWABLE}
        WHERE v.product_id = %s
    """, (product_id,))
    return [r["size_code"] for r in rows]


def price_curve(conn: psycopg.Connection, product_id: int, days: int = 180) -> list[dict[str, Any]]:
    """Cheapest price per day, and the merchant who held it.

    Le marchand sert l'infobulle de la courbe : savoir que le prix a baissé est
    une information, savoir QUI l'a baissé en est une autre, et c'est celle qui
    décide d'un clic. `DISTINCT ON` prend la ligne la moins chère du jour et
    lit son marchand dessus — un `min()` seul rendrait le prix sans dire d'où
    il vient.
    """
    return _rows(conn, """
        SELECT DISTINCT ON (h.observed_on)
               h.observed_on, h.price, m.code AS merchant
        FROM price_history h
        JOIN raw_offer o ON o.id = h.raw_offer_id
        -- `m.affiche` : un marchand mis de côté disparaît aussi de la FICHE, pas
        -- seulement des agrégats. Sans cette ligne, `product_stats` aurait
        -- annoncé « 2 marchands comparés » pendant que le tableau en listait
        -- trois — une incohérence visible du visiteur et muette pour nous.
        JOIN merchant m ON m.id = o.merchant_id AND m.affiche
        WHERE o.product_id = %s AND h.observed_on >= current_date - %s
          AND h.price <> """ + _PRIX_SENTINELLE + """
        ORDER BY h.observed_on, h.price
    """, (product_id, days))


def search(conn: psycopg.Connection, term: str, limit: int = 40) -> list[dict[str, Any]]:
    """Deliberately simple for now: brand or model contains the words typed."""
    words = [w for w in term.split() if len(w) > 1][:4]
    if not words:
        return []
    clauses = " AND ".join(
        ["(p.brand_code ILIKE %s OR p.model_display ILIKE %s)"] * len(words)
    )
    args: list[Any] = []
    for w in words:
        args += [f"%{w}%", f"%{w}%"]
    return _rows(conn, f"""
        SELECT p.slug, p.brand_code, p.model_display, p.colour_code,
               s.cheapest, s.merchant_count, s.image_url, s.best_title,
               c.label_fr AS category_label
        FROM product p
        JOIN product_stats s ON s.product_id = p.id
        JOIN category c ON c.id = p.category_id
        WHERE {clauses} AND s.cheapest IS NOT NULL AND p.status <> 'merged'
        ORDER BY s.merchant_count DESC, s.cheapest
        LIMIT %s
    """, (*args, limit))


def brands(conn: psycopg.Connection, limit: int = 12) -> list[dict[str, Any]]:
    """The brands with the most comparable products — the rail across the top.

    Read rather than hard-coded: a list typed by hand goes stale the first time a
    merchant drops a brand, and this one is on every page.
    """
    return _rows(conn, """
        SELECT p.brand_code, count(*) AS n
        FROM product p JOIN product_stats s ON s.product_id = p.id
        WHERE s.merchant_count >= 2 AND p.brand_code IS NOT NULL AND p.brand_code <> ''
        GROUP BY p.brand_code ORDER BY count(*) DESC LIMIT %s
    """, (limit,))


# --------------------------------------------------------------------- facettes

def facets(conn: psycopg.Connection, f: Filtres) -> dict[str, Any]:
    """The counts beside each filter, computed on what the visitor can see.

    A filter offering a brand with nothing behind it is worse than no filter:
    the visitor clicks and lands on an empty page. Every count therefore comes
    from the same window the listing uses, and a facet with zero results is
    never printed.

    One deliberate exception: each facet is counted with **its own** criterion
    lifted. Counting brands while a brand is already chosen would answer "1
    brand, 40 products" — true, and useless. Lifting it answers "if you switched
    to Shoei, you would get 312", which is the question the visitor is actually
    asking when they open that list.
    """
    def compte(sql: str, sans: str) -> list[dict[str, Any]]:
        args = _args(f)
        if sans == "marque":
            args["b"] = None
        elif sans == "prix":
            args["lo"] = args["hi"] = None
        elif sans == "taille":
            args["ta"] = None
        elif sans == "couleur":
            args["co"] = None
        elif sans == "marchands":
            args["m"] = 2
        elif sans == "categories":
            args["c"] = None
        return _rows(conn, sql, args)

    marques = compte(f"""
        SELECT p.brand_code AS valeur, count(*) AS n
        FROM product p JOIN product_stats s ON s.product_id = p.id
        {_OU} AND p.brand_code IS NOT NULL AND p.brand_code <> ''
        GROUP BY p.brand_code ORDER BY count(*) DESC, p.brand_code LIMIT 18
    """, "marque")

    # La jauge de prix a besoin des bornes réelles de ce que le visiteur voit :
    # proposer 0 à 3 000 EUR sur un rayon de gants n'aide personne.
    bornes = _row(conn, f"""
        SELECT max(s.cheapest) AS maxi, count(*) AS n
        FROM product p JOIN product_stats s ON s.product_id = p.id
        {_OU}
    """, {**_args(f), "lo": None, "hi": None}) or {}

    tailles = compte(f"""
        SELECT v.size_code AS valeur, count(DISTINCT p.id) AS n
        FROM product p
        JOIN product_stats s ON s.product_id = p.id
        JOIN variant v ON v.product_id = p.id
        {_OU} AND v.size_code <> 'TU'
          -- Seulement ce qui EST une taille. Le champ en contient d'autres
          -- choses, héritées des flux : des mots du modèle (MONO, PURE, TECH,
          -- VIB), des finitions (MATT), des références marchand (YM5051), et
          -- des tailles collées à un tour de tête (XXXL6566 — la normalisation
          -- coupe S5556 en S mais ne connaît pas XXXL).
          --
          -- Filtré à l'AFFICHAGE : proposer « MONO » comme taille fait douter
          -- de tout le reste. Le nettoyage des données, lui, demande un
          -- réappariement complet — noté comme suite.
          -- Accolades DOUBLÉES : la requête est une f-string, et Python lisait
          -- `{{0,3}}` comme un champ à formater — le motif partait en
          -- `X(0, 3)[SML]`, qui ne correspond à rien. Aucune erreur levée,
          -- aucune taille affichée : le pire des deux mondes.
          AND (v.size_code ~ '^[2-6]?X{{0,3}}[SML]$' OR v.size_code ~ '^[0-9]{{1,2}}$')
        GROUP BY v.size_code
        HAVING count(DISTINCT p.id) >= 3
        ORDER BY count(DISTINCT p.id) DESC LIMIT 24
    """, "taille")

    couleurs = compte(f"""
        SELECT p.colour_code AS valeur, count(*) AS n
        FROM product p JOIN product_stats s ON s.product_id = p.id
        {_OU} AND p.colour_code IS NOT NULL AND p.colour_code <> 'unknown'
        GROUP BY p.colour_code ORDER BY count(*) DESC LIMIT 16
    """, "couleur")

    # Les catégories : une VRAIE facette, pas l'arbre global.
    #
    # Elles affichaient jusqu'ici le catalogue entier avec ses compteurs
    # entiers — « Casques 3 256 » sur une recherche qui en rend 26. Le panneau
    # répondait donc à une question que le visiteur ne pose pas. Comme les
    # autres facettes, celle-ci est comptée avec SON propre critère levé : elle
    # dit « si vous restreigniez aux casques, vous en auriez 24 ».
    lignes_cat = compte(f"""
        SELECT racine.code AS racine_code, racine.label_fr AS racine_label,
               c.code AS code, c.label_fr AS label_fr,
               c.id = racine.id AS est_racine,
               count(*) AS n
        FROM product p
        JOIN product_stats s ON s.product_id = p.id
        JOIN category c ON c.id = p.category_id
        JOIN category racine ON racine.id = coalesce(c.parent_id, c.id)
        {_OU}
          -- Le seau « Non classé » (25) est le fourre-tout du classificateur,
          -- pas un rayon. 2 624 fiches y dorment parce que leur catégorie n'a
          -- pas pu être lue : en faire une destination, c'est promettre une
          -- étagère qui n'en est pas une. `categories()` l'excluait déjà ;
          -- cette facette-ci l'avait oublié.
          AND c.id <> 25
        GROUP BY racine.code, racine.label_fr, c.code, c.label_fr, est_racine
    """, "categories")

    par_racine: dict[str, dict[str, Any]] = {}
    for ligne in lignes_cat:
        r = par_racine.setdefault(ligne["racine_code"], {
            "code": ligne["racine_code"], "label_fr": ligne["racine_label"],
            "n": 0, "enfants": [],
        })
        r["n"] += ligne["n"]
        if not ligne["est_racine"]:
            r["enfants"].append({"code": ligne["code"], "label_fr": ligne["label_fr"],
                                 "n": ligne["n"]})
    categories = sorted(par_racine.values(), key=lambda r: -r["n"])
    for r in categories:
        r["enfants"].sort(key=lambda e: -e["n"])

    marchands = compte(f"""
        SELECT s.merchant_count AS valeur, count(*) AS n
        FROM product p JOIN product_stats s ON s.product_id = p.id
        {_OU}
        GROUP BY s.merchant_count ORDER BY s.merchant_count DESC
    """, "marchands")

    return {
        "categories": categories,
        "marques": marques,
        "prix_maxi": float(bornes.get("maxi") or 0),
        "tailles": tailles,
        "couleurs": couleurs,
        "marchands": marchands,
    }




@dataclass(frozen=True, kw_only=True)
class Filtres:
    """Everything a visitor can narrow a listing by.

    Grouped in one object rather than passed as eight arguments: the same set
    travels from the route to the listing, to the counts, and back into every
    link on the page, and a positional mix-up between two of them would be
    silent — a wrong listing, no error.

    `kw_only` is not decoration. Adding `texte` in second position while the
    routes still passed by rank sent the brand into the search field: three
    listings broke at once, and the two that did not break would have returned
    quietly wrong results. Named arguments only — a field can now be inserted
    anywhere without touching a caller.
    """

    categories: list[int] | None = None
    texte: str | None = None
    marque: str | None = None
    prix_min: float | None = None
    prix_max: float | None = None
    taille: str | None = None
    couleur: str | None = None
    marchands: int = 2
    tri: str = "pertinence"

    def actifs(self) -> list[dict[str, str]]:
        """The filters actually in force, ready to be shown as removable chips.

        `marchands` is excluded on purpose: 2 is the floor of the whole site — a
        product nobody else sells is not a comparison — so it is a property of
        the catalogue, not a choice the visitor made and can undo.
        """
        out: list[dict[str, str]] = []
        if self.texte:
            out.append({"cle": "q", "texte": f"« {self.texte} »"})
        if self.marque:
            out.append({"cle": "marque", "texte": self.marque.upper()})
        if self.prix_min is not None or self.prix_max is not None:
            bas = f"{self.prix_min:.0f}" if self.prix_min is not None else "0"
            haut = f"{self.prix_max:.0f} €" if self.prix_max is not None else "et +"
            out.append({"cle": "prix", "texte": f"{bas} à {haut}"})
        if self.taille:
            out.append({"cle": "taille", "texte": f"Taille {self.taille}"})
        if self.couleur:
            out.append({"cle": "couleur", "texte": self.couleur})
        if self.marchands > 2:
            out.append({"cle": "marchands", "texte": f"{self.marchands} marchands et +"})
        return out


# The WHERE every listing and every count share, so a facet can never promise a
# result the listing would not show.
_OU = """
    WHERE s.merchant_count >= %(m)s AND s.cheapest IS NOT NULL
      AND p.status <> 'merged'
      AND (%(c)s::smallint[] IS NULL OR p.category_id = ANY(%(c)s::smallint[]))
      AND (%(b)s::text IS NULL OR p.brand_code = %(b)s::text)
      AND (%(lo)s::numeric IS NULL OR s.cheapest >= %(lo)s::numeric)
      AND (%(hi)s::numeric IS NULL OR s.cheapest <= %(hi)s::numeric)
      AND (%(co)s::text IS NULL OR p.colour_code = %(co)s::text)
      AND (%(ta)s::text IS NULL OR EXISTS (
            SELECT 1 FROM variant v
            WHERE v.product_id = p.id AND v.size_code = %(ta)s::text))
      -- La recherche est un filtre comme les autres, et pas une page à part :
      -- c'est ce qui lui donne le même panneau, les mêmes compteurs et le même
      -- tri que le reste du site. Chaque mot doit se trouver quelque part — un
      -- ET, pas un OU : « arai sz » ne doit pas ramener tout Arai.
      --
      -- Le NOM DU RAYON est cherché aussi, et c'est le correctif qui compte :
      -- « casque » ne ramenait que 97 fiches sur 3 256, parce qu'un casque
      -- s'appelle « RPHA 12 » et pas « casque » — le mot n'est que dans sa
      -- catégorie. Le premier résultat était un pare-soleil, et sept
      -- silencieux « carby aluminium/casquette carbone » suivaient. C'est
      -- l'entrée principale du site, et elle ne servait pas à ce qu'elle
      -- annonce.
      --
      -- `unaccent` des deux côtés : sans lui « intégral » ne trouvait rien,
      -- puisque le rayon s'écrit « Casques intégraux » et que l'accent ne
      -- tombait pas au même endroit. Le suffixe est rogné à la comparaison
      -- (« casques » trouve « casque », et l'inverse).
      AND (%(q)s::text[] IS NULL OR NOT EXISTS (
            SELECT 1 FROM unnest(%(q)s::text[]) AS mot
            WHERE unaccent(p.brand_code)    NOT ILIKE '%%' || unaccent(mot) || '%%'
              AND unaccent(p.model_display) NOT ILIKE '%%' || unaccent(mot) || '%%'
              -- sous-requête et non `c.label_fr` : `_OU` est réutilisé par des
              -- requêtes de facettes qui ne joignent pas `category`.
              AND NOT EXISTS (
                    SELECT 1 FROM category cc
                    WHERE cc.id = p.category_id
                      -- le pluriel n'est rogné qu'à partir de quatre lettres :
                      -- « sx » deviendrait sinon la chaîne vide, qui trouve
                      -- tous les rayons.
                      AND unaccent(cc.label_fr) ILIKE '%%' ||
                          unaccent(CASE WHEN length(mot) >= 4
                                        THEN rtrim(mot, 'sx') ELSE mot END) || '%%')))
"""


def _args(f: Filtres) -> dict[str, Any]:
    return {
        "c": f.categories, "b": f.marque or None, "m": f.marchands,
        "lo": f.prix_min, "hi": f.prix_max,
        "ta": f.taille or None, "co": f.couleur or None,
        "q": _mots(f.texte),
    }


def _mots(texte: str | None) -> list[str] | None:
    """Les mots retenus d'une recherche : au plus quatre, d'au moins deux
    lettres. Au-delà de quatre, on filtre sur du bruit ; en deçà de deux, on
    filtre sur rien."""
    if not texte:
        return None
    mots = [m for m in texte.split() if len(m) > 1][:4]
    return mots or None


def listing_filtre(
    conn: psycopg.Connection, f: Filtres, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    """One page of a filtered listing, and how many rows the filter matches."""
    args = {**_args(f), "lim": limit, "off": offset}
    ordres = {
        "pertinence": "s.merchant_count DESC, s.cheapest",
        "prix":       "s.cheapest",
        "prix_desc":  "s.cheapest DESC",
        "marchands":  "s.merchant_count DESC, s.cheapest",
        # `vu_le` est la date de la première offre vue, portée par
        # `product_stats` (migration 020) — jamais `product.created_at`, qui
        # vaut le jour de reconstruction de la table pour tout le catalogue.
        #
        # Ce tri ne parle que de la TÊTE de la liste : 310 770 fiches sur
        # 311 698 portent la date du versement initial et sont donc à égalité.
        # Le nombre de marchands les départage, ce qui revient à dire « après
        # les nouveautés, les mieux comparées ». L'écart se creusera de
        # lui-même à chaque collecte.
        "nouveautes": "s.vu_le DESC NULLS LAST, s.merchant_count DESC",
    }
    # `p.slug` clôt TOUS les tris, et ce n'est pas une précaution de style : sans
    # départage, deux fiches à clé égale sortent dans un ordre libre, que
    # PostgreSQL n'a aucune raison de tenir d'une requête à l'autre. Avec
    # LIMIT/OFFSET, cela veut dire une fiche vue deux fois page 3 et jamais
    # page 4. Le tri « Nouveautés » rend le défaut criant — 310 770 ex æquo —
    # mais il concernait déjà les quatre autres.
    ordre = ordres.get(f.tri, ordres["pertinence"]) + ", p.slug"

    items = _rows(conn, f"""
        SELECT p.slug, p.brand_code, p.model_display, p.colour_code,
               s.cheapest, s.dearest, s.merchant_count, s.image_url, s.best_title,
               c.label_fr AS category_label
        FROM product p
        JOIN product_stats s ON s.product_id = p.id
        JOIN category c ON c.id = p.category_id
        {_OU}
        ORDER BY {ordre}
        LIMIT %(lim)s OFFSET %(off)s
    """, args)

    row = _row(conn, f"""
        SELECT count(*) AS n
        FROM product p JOIN product_stats s ON s.product_id = p.id
        {_OU}
    """, args)
    return items, int(row["n"]) if row else 0





def toutes_marques(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Every brand that has at least one comparable product, with its count.

    « Toutes les marques » de la v1. Le seuil est le même que partout ailleurs :
    une marque qu'un seul marchand vend n'a rien à comparer, elle encombrerait
    un index déjà long sans rien apporter au visiteur.
    """
    return _rows(conn, """
        SELECT p.brand_code, count(*) AS n
        FROM product p JOIN product_stats s ON s.product_id = p.id
        WHERE s.merchant_count >= 2
          AND p.brand_code IS NOT NULL AND p.brand_code <> ''
        GROUP BY p.brand_code
        ORDER BY p.brand_code
    """)


def bons_plans(conn: psycopg.Connection, limit: int = 48) -> list[dict[str, Any]]:
    """Les vraies affaires : le même CODE-BARRES, deux marchands, deux prix.

    Première version écrite sur l'écart de la fiche, comme la rangée de
    l'accueil. Mesurée, elle sortait une page entière d'articles à « -50 % »
    qui n'étaient pas des affaires du tout : une fiche SW-Motech contenant à la
    fois un kit de sacoches 16 L à 350 € et un kit 16/16 L à 675 €, pour deux
    motos différentes. L'écart existait, mais entre deux articles différents.

    Comparer deux prix n'a de sens qu'à produit identique, et le seul niveau où
    « identique » est prouvé, c'est le code-barres. C'est donc lui qui porte la
    page. Le plafond d'un facteur deux reste, pour la raison d'avant : au-delà,
    c'est presque toujours un défaut de données.
    """
    return _rows(conn, """
        WITH par_marchand AS (
            -- Un prix par marchand : le sien, le meilleur. Sans cette étape,
            -- `min` et `max` pouvaient sortir du MÊME marchand (A à 100 € et
            -- 200 €, B à 150 € : la page annonçait « 100 € d'écart entre
            -- marchands » pour un écart interne à A).
            SELECT o.gtin, o.merchant_id,
                   min(o.price) AS prix,
                   (array_agg(o.product_id ORDER BY o.product_id))[1] AS product_id,
                   (array_agg(o.image_url ORDER BY o.image_url)
                        FILTER (WHERE o.image_url IS NOT NULL))[1]    AS image_url
            FROM raw_offer o
            WHERE """ + _SHOWABLE + """ AND o.gtin IS NOT NULL
              AND o.price IS NOT NULL AND o.price > 0 AND o.in_stock IS NOT FALSE
            GROUP BY o.gtin, o.merchant_id
        ),
        par_gtin AS (
            SELECT gtin,
                   min(prix) AS cheapest,
                   max(prix) AS dearest,
                   count(*)  AS merchant_count,
                   -- `ORDER BY` explicite : sans lui, le choix de la fiche est
                   -- indéterminé, et le slug affiché pouvait venir d'une fiche
                   -- pendant que les prix venaient d'une autre.
                   (array_agg(product_id ORDER BY product_id))[1] AS product_id,
                   (array_agg(image_url ORDER BY image_url)
                        FILTER (WHERE image_url IS NOT NULL))[1]   AS image_url
            FROM par_marchand
            GROUP BY gtin
            HAVING count(*) >= 2
               -- 1,9 et non 2 : le plafond exact concentrait en tête de page
               -- les lignes collées à la limite, c'est-à-dire celles que le
               -- projet déclare lui-même douteuses.
               AND max(prix) <= min(prix) * 1.9
               AND min(prix) >= 15
        ),
        avec_fiche AS (
            -- une ligne par modèle : le même casque en sept tailles, ce sont
            -- sept codes-barres, et sept fois la même affaire à l'écran.
            SELECT DISTINCT ON (p.brand_code, p.model_display, p.colour_code)
                   g.*, p.slug, p.brand_code, p.model_display, p.colour_code,
                   round((1 - g.cheapest / g.dearest) * 100) AS remise
            FROM par_gtin g
            JOIN product p ON p.id = g.product_id
            WHERE p.status <> 'merged'
            ORDER BY p.brand_code, p.model_display, p.colour_code,
                     (g.dearest - g.cheapest) DESC
        ),
        classe AS (
            SELECT *, row_number() OVER (PARTITION BY brand_code
                                         ORDER BY (dearest - cheapest) DESC) AS rang
            FROM avec_fiche
        )
        -- trois articles par marque au maximum : sinon un seul équipementier
        -- occupe toute la page, et le motard venu pour un casque n'y trouve
        -- que des échappements.
        SELECT * FROM classe
        WHERE remise >= 10 AND rang <= 3
        -- Par pourcentage : c'est ce qu'un acheteur lit comme une affaire. Par
        -- gain absolu, la page entière devenait des blousons à 1 500 €, et le
        -- motard venu comparer des gants n'y trouvait rien.
        ORDER BY remise DESC, (dearest - cheapest) DESC
        LIMIT %s
    """, (limit,))


def marchands_actifs(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Les marchands qui apparaissent vraiment sur au moins une fiche comparable.

    Écrit en dur, ce nombre mentait : le site annonçait « 6 marchands vérifiés »
    alors que Maxxess et Moto-Axxe, dont les codes-barres sont fabriqués, ne
    parvenaient à se rattacher à aucune fiche — zéro offre visible, sur les deux.
    Un visiteur pouvait le vérifier lui-même en trois clics dans les filtres.

    Il se lit donc en base, et il redeviendra 5 ou 6 tout seul le jour où ces
    marchands seront rattachés, sans que personne ait à y repenser.
    """
    return _rows(conn, """
        SELECT m.code, count(DISTINCT o.product_id) AS fiches
        FROM merchant m
        JOIN raw_offer o ON o.merchant_id = m.id AND """ + _SHOWABLE + """
        GROUP BY m.code
        HAVING count(DISTINCT o.product_id) > 0
        ORDER BY count(DISTINCT o.product_id) DESC
    """)


# ------------------------------------------------------- la barre de recherche

def marques_par_rayon(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Chaque marque, ventilée par rayon, avec son nombre de fiches comparables.

    C'est la matière de l'entonnoir : taper « arai » doit pouvoir répondre
    « Arai dans Casques (142) », « Arai dans Accessoires (3) ».

    Tout est calculé d'un coup et gardé en mémoire, parce que le résultat est
    minuscule et qu'il ne bouge qu'au passage du pipeline. Mesuré le 17/09/2026
    sur 313 435 fiches : **711 lignes, 217 marques, 70 Ko, 157 ms**.

    L'alternative — une requête par frappe — coûtait 130 ms de base à chaque
    lettre tapée, parce que `f_unaccent(brand_code)` empêche l'index de servir
    et force un balayage des 313 000 fiches. Sur un VPS à un cœur, taper
    « alpinestars » aurait lancé douze balayages complets.
    """
    return _rows(conn, """
        SELECT lower(p.brand_code) AS marque, c.id AS rayon_id,
               c.code AS rayon_code, c.label_fr AS rayon, count(*) AS n
        FROM product p
        JOIN product_stats s ON s.product_id = p.id
        JOIN category c ON c.id = p.category_id
        WHERE s.merchant_count >= 2 AND s.cheapest IS NOT NULL
          AND p.status <> 'merged'
          AND p.brand_code IS NOT NULL AND p.brand_code <> ''
        GROUP BY 1, 2, 3, 4
    """)


# Quatre mots au maximum. Au-delà, chaque mot ajoute une condition sur la même
# expression indexée et le gain devient nul : personne ne tape cinq mots dans
# une barre de recherche de comparateur, et s'il le fait, les quatre premiers
# suffisent largement à cerner le produit.
_MAX_MOTS = 4

# On cherche dans le TITRE MARCHAND, pas dans notre nom reconstruit.
#
# `model_display` est un sac de jetons trié par ordre alphabétique : le casque
# « Arai SZ-R VAS EVO » y devient « Evo R Sz Vas », et personne ne tape ça.
# `best_title` est ce que le marchand écrit, dans l'ordre où il l'écrit.
#
# `f_recherche` (migration 018) recolle la ponctuation : « SZ-R » devient
# « szr ». Sans cela pg_trgm y voit deux mots, « sz » et « r », et quelqu'un qui
# tape « szr » ne rencontre ni l'un ni l'autre. L'expression est EXACTEMENT
# celle de l'index — une autre serait ignorée en silence, et chaque frappe
# balaierait 311 000 lignes.
_EXPRESSION = "f_recherche(s.best_title)"

_CHAMPS = """p.slug, p.model_display, s.best_title, p.brand_code,
             p.colour_code, s.image_url, s.cheapest, s.merchant_count"""

_FILTRE = """s.merchant_count >= 2 AND s.cheapest IS NOT NULL
             AND p.status <> 'merged'"""


def _score(nb: int) -> str:
    """La somme des ressemblances, un terme par mot tapé."""
    if not nb:
        return "0"
    return " + ".join(
        f"strict_word_similarity(%(m{i})s, {_EXPRESSION})" for i in range(nb))


def produits_dans_la_marque(conn: psycopg.Connection, marque: str,
                            mots: list[str], limite: int = 6
                            ) -> list[dict[str, Any]]:
    """Les fiches d'UNE marque, classées par ressemblance aux mots restants.

    La marque une fois reconnue, on ne cherche plus que dans son catalogue —
    quelques centaines de fiches. On peut donc classer par ressemblance SANS
    seuil, et c'est ce qui rattrape les fautes de frappe : « zzr » ne ressemble
    à « szr » qu'à 0,14, bien trop peu pour franchir un seuil, mais c'est
    suffisant pour arriver premier parmi les 147 Arai.

    Mesuré le 17/09/2026 : « arai zzr » rend le SZ-R VAS EVO en tête, en 74 ms.
    """
    mots = [m for m in mots if m][:_MAX_MOTS]
    args: dict[str, Any] = {f"m{i}": m for i, m in enumerate(mots)}
    args["marque"] = marque
    args["limite"] = limite
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
            SELECT {_CHAMPS}, ({_score(len(mots))}) AS score
            FROM product_stats s JOIN product p ON p.id = s.product_id
            WHERE {_FILTRE} AND p.brand_code = %(marque)s
            ORDER BY score DESC, s.merchant_count DESC, s.cheapest
            LIMIT %(limite)s
        """, args)
        return cur.fetchall()


def produits_suggeres(conn: psycopg.Connection, mots: list[str],
                      limite: int = 6) -> list[dict[str, Any]]:
    """Les fiches où CHAQUE mot tapé apparaît.

    Une seule condition sur la chaîne entière ne trouvait rien pour « ixon bl » :
    notre `model_display` est un sac de jetons trié alphabétiquement, si bien que
    « Ixon Blanky » y devient « Blanky ixon » et que la marque ne précède jamais
    le modèle. Mot par mot, l'ordre n'a plus d'importance — et c'est l'index de
    trigrammes qui sert chaque condition.
    """
    mots = [m for m in mots if m][:_MAX_MOTS]
    if not mots:
        return []
    # `<<%` : « ce mot ressemble-t-il à un mot entier de ce texte ». C'est
    # l'opérateur que sert l'index de trigrammes, et c'est la version STRICTE —
    # l'extrait comparé doit commencer et finir sur une frontière de mot.
    #
    # Sans « strict », chercher « ara » proposait une veste Ixon OSTARA, une
    # araignée SW-Motech et des gants Dainese KARAKUM : trois mots qui
    # contiennent ces lettres au milieu, et qu'aucun visiteur ne cherchait.
    conditions = " AND ".join(
        f"%(m{i})s <<% {_EXPRESSION}".replace("<<%", "<<%%")
        for i in range(len(mots)))
    args: dict[str, Any] = {f"m{i}": m for i, m in enumerate(mots)}
    args["limite"] = limite
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
            SELECT {_CHAMPS}, ({_score(len(mots))}) AS score
            FROM product_stats s JOIN product p ON p.id = s.product_id
            WHERE {_FILTRE} AND {conditions}
            ORDER BY score DESC, s.merchant_count DESC, s.cheapest
            LIMIT %(limite)s
        """, args)
        return cur.fetchall()


# --- caractéristiques produit --------------------------------------------------
#
# Trois sources écrivent dans `product_caracteristique`, et peuvent se
# retrouver sur le MÊME nom pour la MÊME fiche : `poids_g` existe côté flux
# (annoncé par un marchand), côté revendeur (lu en prose) et
# côté SHARP (pesé en laboratoire). Depuis la migration 025, les trois lignes
# coexistent — c'est ICI, à la lecture, que le choix se fait, jamais à
# l'écriture. Une mesure de laboratoire prime sur une annonce de revendeur, qui
# prime sur une description marchande : c'est l'ordre inverse de la facilité à
# obtenir la donnée, et c'est voulu.
_SOURCE_PRIORITE = {"sharp": 0, "revendeur": 1, "flux": 2}

# Pour certains noms, la priorité par défaut ne s'applique pas.
# Le poids SHARP est mesuré en laboratoire, mais avec une seule taille de
# référence ; le revendeur le lit dans la fiche technique du modèle exact.
# On préfère donc revendeur > flux > sharp pour poids_g.
_SOURCE_PRIORITE_PAR_NOM: dict[str, dict[str, int]] = {
    "poids_g": {"revendeur": 0, "flux": 1, "sharp": 2},
}

# Noms anciens → nom canonique. Les lignes SHARP antérieures à la migration
# 025 ont été écrites avec nom='poids' ; le rapprochement en écrira 'poids_g'
# à la prochaine passe, mais en attendant on fusionne les deux à la lecture.
_NOM_ALIAS: dict[str, str] = {"poids": "poids_g"}

# Le libellé affiché, et RIEN d'autre — jamais la valeur, qui reste celle
# écrite par l'extracteur. Un nom absent de ce dictionnaire s'affiche quand
# même : `caracteristiques()` refait un libellé lisible à partir du nom brut,
# pour qu'un nouveau rayon ne laisse jamais une caractéristique invisible en
# attendant qu'on pense à l'ajouter ici.
_LIBELLES: dict[str, str] = {
    # communes à plusieurs rayons
    "matiere": "Matière", "matiere_coque": "Matière de la coque",
    "matiere_nommee": "Matière précise", "matiere_renforcee": "Renfort",
    "homologation": "Homologation ECE", "note_securite": "Note de sécurité SHARP",
    "poids_g": "Poids", "saison": "Saison", "univers": "Univers de pratique",
    "genre": "Genre", "impermeable": "Imperméable", "gore_tex": "Gore-Tex",
    "membrane": "Membrane imperméable", "membrane_nom": "Membrane",
    "doublure_thermique": "Doublure thermique",
    "doublure_thermique_amovible": "Doublure thermique amovible",
    "ventilation": "Ventilation", "ventilations": "Ventilation",
    "reflechissant": "Éléments réfléchissants",
    "elements_reflechissants": "Éléments réfléchissants",
    "reflechissants": "Éléments réfléchissants",
    # casque
    "calotte": "Matière de la calotte", "boucle": "Type de fermeture",
    "pinlock": "Pinlock", "ecran_solaire": "Écran solaire intégré",
    "interieur_amovible": "Intérieur amovible", "intercom": "Intercom",
    "nombre_coques": "Tailles de coque disponibles",
    # blouson / combinaison
    "norme_en17092": "Norme EN 17092", "classe_protection": "Classe de protection",
    "protections_epaules": "Protections épaules", "protections_coudes": "Protections coudes",
    "dorsale": "Protection dorsale", "poche_dorsale": "Poche à dorsale",
    "reglages_serrage": "Réglages de serrage", "zip_liaison_pantalon": "Zip de liaison pantalon",
    # gant
    "chauffant": "Chauffant", "niveau": "Niveau EN 13594", "kp": "Protection articulations (KP)",
    "matiere_paume": "Matière de la paume", "matiere_dos": "Matière du dos",
    "coque_articulations": "Coque de protection", "slider_paume": "Slider de paume",
    "renfort_paume": "Renfort de paume", "protection_scaphoide": "Protection du scaphoïde",
    "manchette": "Longueur de manchette", "tactile": "Compatible écran tactile",
    # pantalon
    "categorie": "Type", "renfort_aramide": "Renfort aramide",
    "etendue_aramide": "Étendue du renfort aramide", "coques_genoux": "Coques genoux",
    "niveau_genoux": "Niveau de protection (genoux)", "coques_hanches": "Coques hanches",
    "niveau_hanches": "Niveau de protection (hanches)",
    "genouilleres_reglables": "Genouillères réglables",
    "emplacement_slider": "Emplacement slider", "zip_liaison": "Zip de liaison veste",
    "coupe": "Coupe",
    # botte
    "protection_malleole": "Protection de malléole", "protection_selecteur": "Protection de sélecteur",
    "protection_tibia": "Protection du tibia", "indice_hauteur": "Indice de hauteur (EN 13634)",
    "indice_abrasion": "Indice d'abrasion (EN 13634)", "indice_coupure": "Indice de coupure (EN 13634)",
    "indice_rigidite": "Indice de rigidité (EN 13634)", "coque_bout_de_pied": "Coque au bout du pied",
    "fermeture": "Fermeture", "semelle_antiderapante": "Semelle antidérapante",
    "semelle_anti_huile": "Semelle anti-huile",
}

# Les mots qu'une valeur peut prendre, tels qu'écrits par les extracteurs, vers
# ce qu'on affiche. `True`/`False` sont la représentation texte d'un booléen
# Python — `_ecrire()` fait `str(valeur)`, jamais autre chose — et un extracteur
# qui ajoute un mot nouveau (« fourni », « polycarbonate »…) s'affiche déjà
# correctement sans entrer ici : cette table ne couvre QUE les booléens.
_VALEURS = {"True": "Oui", "False": "Non"}


def caracteristiques(conn: psycopg.Connection, product_id: int) -> list[dict[str, Any]]:
    """Les caractéristiques d'une fiche, une par nom, la source la plus fiable
    d'abord quand plusieurs sources répondent sur le même nom.

    Rend une liste plutôt qu'un dict : l'ordre — SHARP et le revendeur en tête,
    reconnaissables par leur badge, puis le reste — est une information que le
    gabarit ne doit pas avoir à recalculer.
    """
    lignes = _rows(conn, """
        SELECT nom, valeur, source, confiance
        FROM product_caracteristique
        WHERE product_id = %s
        ORDER BY nom
    """, (product_id,))

    par_nom: dict[str, dict[str, Any]] = {}
    for l in lignes:
        nom = _NOM_ALIAS.get(l["nom"], l["nom"])
        priorite = _SOURCE_PRIORITE_PAR_NOM.get(nom, _SOURCE_PRIORITE)
        retenue = par_nom.get(nom)
        if retenue is None or (priorite.get(l["source"], 9)
                               < priorite.get(retenue["source"], 9)):
            par_nom[nom] = {**l, "nom": nom}

    resultat = []
    for nom, l in par_nom.items():
        resultat.append({
            "nom": nom,
            "libelle": _LIBELLES.get(nom) or nom.replace("_", " ").capitalize(),
            "valeur": _VALEURS.get(l["valeur"], l["valeur"]),
            "source": l["source"],
            "confiance": l["confiance"],
        })
    # SHARP et le revendeur en tête : ce sont les deux seules sources qui ne
    # viennent pas du texte de vente d'un marchand, et la fiche doit le
    # montrer d'un coup d'œil plutôt que de les noyer par ordre alphabétique.
    resultat.sort(key=lambda c: (_SOURCE_PRIORITE.get(c["source"], 9), c["libelle"]))
    return resultat


# --- le comparateur -------------------------------------------------------
#
# Ce que les marchands se disputent d'abord sur un équipement de sécurité,
# ce n'est pas le prix : c'est la protection. Les noms ci-dessous montent en
# tête du tableau ; tout le reste suit par ordre alphabétique de libellé,
# jamais perdu — un nom absent de cette liste atterrit simplement après.
_PROTECTION_EN_TETE = [
    "note_securite", "homologation", "norme_en17092", "classe_protection",
    "niveau", "kp", "niveau_genoux", "niveau_hanches",
    "indice_hauteur", "indice_abrasion", "indice_coupure", "indice_rigidite",
    "dorsale", "poche_dorsale", "protections_epaules", "protections_coudes",
    "coque_articulations", "protection_scaphoide",
    "coque_bout_de_pied", "protection_malleole", "protection_selecteur",
    "protection_tibia", "coques_genoux", "coques_hanches",
    "nombre_coques", "calotte", "matiere_coque",
]
_RANG_PROTECTION = {nom: i for i, nom in enumerate(_PROTECTION_EN_TETE)}

# Les sections repliables du tableau — l'ordre ici EST l'ordre affiché.
# « Protection & sécurité » ouvre toujours le tableau, pour la même raison que
# `_PROTECTION_EN_TETE` ci-dessus : c'est la question qu'on pose en premier
# sur un équipement dont le métier est de protéger, pas de plaire.
_ORDRE_SECTIONS = [
    "Protection & sécurité", "Matériaux", "Confort & ajustement",
    "Climat & météo", "Options & technologies", "Usage",
]
_SECTION_PAR_NOM: dict[str, str] = {
    "note_securite": "Protection & sécurité", "homologation": "Protection & sécurité",
    "norme_en17092": "Protection & sécurité", "classe_protection": "Protection & sécurité",
    "niveau": "Protection & sécurité", "kp": "Protection & sécurité",
    "niveau_genoux": "Protection & sécurité", "niveau_hanches": "Protection & sécurité",
    "indice_hauteur": "Protection & sécurité", "indice_abrasion": "Protection & sécurité",
    "indice_coupure": "Protection & sécurité", "indice_rigidite": "Protection & sécurité",
    "dorsale": "Protection & sécurité", "poche_dorsale": "Protection & sécurité",
    "protections_epaules": "Protection & sécurité", "protections_coudes": "Protection & sécurité",
    "coque_articulations": "Protection & sécurité", "protection_scaphoide": "Protection & sécurité",
    "coque_bout_de_pied": "Protection & sécurité", "protection_malleole": "Protection & sécurité",
    "protection_selecteur": "Protection & sécurité", "protection_tibia": "Protection & sécurité",
    "coques_genoux": "Protection & sécurité", "coques_hanches": "Protection & sécurité",
    "nombre_coques": "Protection & sécurité", "poids_g": "Protection & sécurité",
    "genouilleres_reglables": "Protection & sécurité",
    "matiere": "Matériaux", "matiere_coque": "Matériaux", "matiere_nommee": "Matériaux",
    "matiere_renforcee": "Matériaux", "calotte": "Matériaux", "matiere_paume": "Matériaux",
    "matiere_dos": "Matériaux", "renfort_aramide": "Matériaux", "etendue_aramide": "Matériaux",
    "boucle": "Confort & ajustement", "manchette": "Confort & ajustement",
    "reglages_serrage": "Confort & ajustement", "zip_liaison_pantalon": "Confort & ajustement",
    "zip_liaison": "Confort & ajustement", "emplacement_slider": "Confort & ajustement",
    "slider_paume": "Confort & ajustement", "renfort_paume": "Confort & ajustement",
    "fermeture": "Confort & ajustement",
    "impermeable": "Climat & météo", "gore_tex": "Climat & météo", "membrane": "Climat & météo",
    "membrane_nom": "Climat & météo", "doublure_thermique": "Climat & météo",
    "doublure_thermique_amovible": "Climat & météo", "ventilation": "Climat & météo",
    "ventilations": "Climat & météo", "chauffant": "Climat & météo",
    "pinlock": "Options & technologies", "ecran_solaire": "Options & technologies",
    "interieur_amovible": "Options & technologies", "intercom": "Options & technologies",
    "tactile": "Options & technologies", "reflechissant": "Options & technologies",
    "elements_reflechissants": "Options & technologies", "reflechissants": "Options & technologies",
    "saison": "Usage", "univers": "Usage", "genre": "Usage", "categorie": "Usage",
    "coupe": "Usage", "semelle_antiderapante": "Usage", "semelle_anti_huile": "Usage",
}
_AUTRES = "Autres caractéristiques"

# Le sens dans lequel une valeur est meilleure — seulement pour ce qui se
# compare vraiment. La matière ou la couleur d'une boucle n'ont pas de
# meilleur sens ; un nom absent d'ici ne reçoit jamais de « gagnant ».
_SENS = {
    "note_securite": "max", "poids_g": "min", "nombre_coques": "max",
    "niveau": "max", "kp": "max", "niveau_genoux": "max", "niveau_hanches": "max",
    "indice_hauteur": "max", "indice_abrasion": "max", "indice_coupure": "max",
    "indice_rigidite": "max", "homologation": "max",
}


def _valeur_numerique(nom: str, valeur: str) -> float | None:
    """`valeur` telle qu'écrite par l'extracteur, ramenée à un nombre quand la
    comparaison en a un — sinon `None`, et la ligne ne désigne aucun gagnant.

    `homologation` est un texte (« 22.06 ») mais se compare comme un nombre :
    la norme la plus récente porte le chiffre le plus haut.
    """
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


def tableau_comparaison(produits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Une ligne par caractéristique, une colonne par produit — l'UNION de ce
    que chaque fiche a su lire, jamais l'intersection : un blouson muet sur sa
    doublure ne doit pas faire disparaître la ligne pour celui qui la précise,
    la cellule reste vide à sa place.

    Chaque produit de `produits` doit déjà porter sa clé `caracteristiques`
    (voir `caracteristiques()`) — récupérée à part, une requête par fiche,
    parce que le nombre de fiches comparées reste petit (huit au plus, posé
    par la route) et que la fusionner ici évite une jointure de plus dans une
    requête déjà chargée.

    Chaque ligne porte sa `section` (pour le regroupement en blocs repliables
    du gabarit) et, quand `_SENS` sait ordonner la caractéristique, le ou les
    `gagnants` — la ou les fiches qui portent la meilleure valeur. Une égalité
    désigne plusieurs gagnants plutôt qu'aucun : deux casques à 5 étoiles SHARP
    se valent, aucune raison d'en avantager un.
    """
    par_nom: dict[str, dict[str, Any]] = {}
    for p in produits:
        for c in p.get("caracteristiques") or []:
            entree = par_nom.setdefault(
                c["nom"], {"nom": c["nom"], "libelle": c["libelle"], "valeurs": {}})
            entree["valeurs"][p["slug"]] = c

    lignes = list(par_nom.values())
    for l in lignes:
        l["section"] = _SECTION_PAR_NOM.get(l["nom"], _AUTRES)
    lignes.sort(key=lambda l: (
        _ORDRE_SECTIONS.index(l["section"]) if l["section"] in _ORDRE_SECTIONS
        else len(_ORDRE_SECTIONS),
        _RANG_PROTECTION.get(l["nom"], 999), l["libelle"]))

    # Une ligne où tout le monde dit la même chose n'aide pas à choisir ; le
    # gabarit s'en sert pour l'atténuer, jamais pour la retirer — une valeur
    # absente ailleurs reste une information (« cette fiche ne le dit pas »).
    for l in lignes:
        vues = {v["valeur"] for v in l["valeurs"].values()}
        l["differe"] = len(vues) > 1

        sens = _SENS.get(l["nom"])
        l["gagnants"] = set()
        if sens and len(l["valeurs"]) > 1:
            notes = {slug: _valeur_numerique(l["nom"], v["valeur"])
                     for slug, v in l["valeurs"].items()}
            notes = {s: n for s, n in notes.items() if n is not None}
            if len(notes) > 1:
                meilleure = (max if sens == "max" else min)(notes.values())
                l["gagnants"] = {s for s, n in notes.items() if n == meilleure}
    return lignes


def sections_comparaison(
    lignes: list[dict[str, Any]]
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Les lignes de `tableau_comparaison()`, groupées par section, dans
    l'ordre d'affichage — pas celui, alphabétique, que le filtre Jinja
    `groupby` imposerait en triant lui-même la liste avant de la grouper.
    `lignes` est déjà trié par section puis par libellé ; grouper ici ne fait
    que replier ce tri, jamais le refaire.
    """
    groupes: dict[str, list[dict[str, Any]]] = {}
    for l in lignes:
        groupes.setdefault(l["section"], []).append(l)
    ordre = _ORDRE_SECTIONS + [s for s in groupes if s not in _ORDRE_SECTIONS]
    return [(s, groupes[s]) for s in ordre if s in groupes]


# --- l'indice de protection MotoComparo -----------------------------------
#
# ⚠️ DÉLIBÉRÉMENT ABSENT DES DONNÉES STRUCTURÉES (`app._donnees_structurees`).
# Cet indice EST un jugement du site sur le produit — à la différence des
# cinq étoiles de la fiche, qui ne notent que le comparateur lui-même. Le
# déclarer comme `Product.aggregateRating` dans le JSON-LD ferait dire à
# Google que MotoComparo a testé et noté l'article, ce qui est faux et fait
# perdre les résultats enrichis. Il reste donc un AFFICHAGE, jamais une
# DONNÉE : personne d'extérieur au site ne le lit par un flux.
#
# CE QUI LE FONDE, ET CE QUE LA PAGE DOIT EN DIRE
# ===============================================
# Une première version n'acceptait de le calculer QUE sur une mesure ou une
# norme indépendante — SHARP pour les casques, une classe EN pour le reste.
# L'intention était juste, le résultat inutilisable : mesuré le 2026-09-24 sur
# les fiches à deux marchands ou plus, l'indice n'apparaissait que sur 19,5 %
# des casques, 35,9 % des blousons et 2,2 % des bottes. Il jetait au passage
# 2 692 matières de calotte, 2 767 protections de coudes et 1 048 protections
# de malléole — des faits lus, du même statut que ceux que la fiche affiche
# déjà ligne par ligne. Refuser de s'en servir pour noter ce qu'on accepte
# d'afficher n'était pas de la prudence, c'était une incohérence.
#
# La règle est donc devenue : toute caractéristique de protection compte, et
# c'est le POIDS qui fait la différence entre une mesure de laboratoire et une
# coque annoncée par un vendeur. Deux garde-fous conservés :
#
#   1. DEUX CRITÈRES MINIMUM. Un seul « Oui » donnerait 10/10 sur une fiche
#      dont on ne sait presque rien — le plus sûr moyen de faire passer un
#      manque d'information pour de l'excellence.
#   2. L'INDICE DIT CE QU'IL VAUT. Le nombre de critères et la présence (ou
#      l'absence) d'une norme indépendante repartent avec la note, et la page
#      les affiche à côté. Un 8,5 fondé sur SHARP et le poids pesé ne se lit
#      pas comme un 8,5 fondé sur deux cases cochées dans une description.
def _echelonne(valeur: float | None, bas: float, haut: float) -> float | None:
    """`valeur` ramenée entre 0 et 10 sur l'intervalle [bas, haut]. `bas` peut
    être plus grand que `haut` — c'est ainsi qu'un poids, où MOINS vaut MIEUX,
    s'échelonne avec la même fonction qu'une note où PLUS vaut mieux."""
    if valeur is None:
        return None
    portee = haut - bas
    if portee == 0:
        return 5.0
    return max(0.0, min(10.0, (valeur - bas) / portee * 10))


_CALOTTE_VERS_NOTE = {
    "carbone": 10.0, "fibre": 9.0, "composite": 7.0,
    "polycarbonate": 5.0, "thermoplastique": 4.0,
}
_NORME_EN17092_VERS_NOTE = {"AAA": 10.0, "AA": 8.5, "A": 6.5, "B": 5.0, "C": 2.0}


# FOURNIE N'EST PAS PRÉPARÉE, ET C'EST TOUT LE SUJET.
#
# Les extracteurs ne rendent pas des booléens sur ces champs-là mais un
# vocabulaire à trois temps, et c'est une chance : « dorsale incluse » veut
# dire qu'on l'a, « option-poche » qu'il y a un logement vide, et
# « option-predisposee » qu'il faudra l'acheter. Les traiter tous comme un
# « Oui » noterait de la même façon un blouson livré protégé et un blouson
# livré avec une fermeture éclair — la confusion exacte que ce site existe
# pour dissiper.
#
# Un « Non » ne descend pas à 0 : l'absence d'un renfort ne fait pas d'un
# vêtement certifié une pièce sans protection, et un zéro écraserait la
# moyenne entière pour une case décochée.
_EQUIPEMENT_VERS_NOTE = {
    "incluse": 10.0, "inclus": 10.0, "fournie": 10.0, "fournies": 10.0,
    "fourni": 10.0, "fournis": 10.0, "oui": 10.0,
    "option-poche": 5.0, "poche": 5.0,
    "option-predisposee": 4.0, "predisposee": 4.0,
    "prepare": 4.0, "prepares": 4.0, "preparee": 4.0, "preparees": 4.0,
    "non": 3.0,
}


def _equipement_vers_note(valeur: str | None, plafond: float = 10.0) -> float | None:
    """Ce que vaut un équipement de protection, de « fourni » à « absent ».

    `plafond` abaisse le maximum du critère quand la chose elle-même vaut
    moins : une poche à dorsale plafonne à 6 — c'est un logement, pas une
    protection — et une protection de sélecteur à 7, parce qu'elle protège la
    botte plus que le pied.
    """
    if not valeur:
        return None
    note = _EQUIPEMENT_VERS_NOTE.get(valeur.strip().lower())
    return None if note is None else min(note, plafond)


# Les classes de l'EN 17092, de la plus protectrice à la moins.
_CLASSE_VERS_NOTE = {"AAA": 10.0, "AA": 8.5, "A": 6.5, "B": 5.0, "C": 2.0}


def _classe_en17092(*valeurs: str | None) -> float | None:
    """La classe EN 17092 d'un blouson, cherchée dans l'ordre des candidats.

    Elle se range selon les fiches dans `classe_protection` OU dans
    `homologation` (« AA » y côtoie « CE » et « EN 13634 » : le champ sert de
    fourre-tout d'homologation, tous rayons confondus). `norme_en17092`, lui,
    ne dit QUE la présence de la norme — jamais le niveau. Une première
    version le lisait en premier, trouvait « Oui », n'y reconnaissait aucune
    classe et abandonnait sans jamais regarder les deux autres : 2,3 % des
    blousons notés au lieu de 36 %.
    """
    for v in valeurs:
        if v:
            note = _CLASSE_VERS_NOTE.get(v.strip().upper())
            if note is not None:
                return note
    return None


def _certifie(valeur: str | None) -> float | None:
    """« Certifié, mais on ne sait pas à quel niveau. »

    C'est une information réelle — une pièce certifiée a passé des essais
    qu'une pièce non certifiée n'a pas passés — et c'est la SEULE qu'on en
    tire. D'où une note médiane, et un poids inférieur à celui d'une classe
    connue : on ne devine pas le niveau qu'on n'a pas lu.
    """
    return 6.0 if valeur else None


def _homologation_nommee(valeur: str | None, norme: str) -> float | None:
    """La norme NOMMÉE vaut mieux qu'un « CE » générique, et c'est mesurable.

    Le champ `homologation` des bottes et des gants porte trois états bien
    distincts : la norme du rayon (« EN 13634 », « EN 13594 »), un « CE » seul
    quand le marchand ne la nomme pas, ou rien. L'extracteur s'interdit déjà
    de confondre les deux premiers — voir `botte._homologation`. C'est, pour
    ces deux rayons, le seul critère GRADUÉ que les descriptions fournissent
    en nombre : tout le reste y est une case cochée qui ne l'est jamais à
    « non ».
    """
    if not valeur:
        return None
    v = valeur.strip().upper()
    if norme.upper() in v:
        return 8.0
    return 5.0 if v == "CE" else None


def _moyenne(*notes: float | None) -> float | None:
    """La moyenne des notes présentes, `None` si aucune ne l'est."""
    connues = [n for n in notes if n is not None]
    return sum(connues) / len(connues) if connues else None


# Le nombre de critères en dessous duquel on préfère ne rien dire. Voir le
# garde-fou 1 du commentaire de section : à un seul critère, l'indice ne note
# plus le produit, il note ce qu'on sait de lui.
_CRITERES_MINIMUM = 2

# GARDE-FOU 3 : UN CRITÈRE QUI NE VARIE JAMAIS NE CLASSE RIEN.
#
# Mesuré le 2026-09-24 sur les bottes : `protection_malleole` vaut « oui »
# 2 017 fois et « non » zéro fois, comme `protection_tibia`, `coque_bout_de_pied`
# et `protection_selecteur`. Un indice bâti sur ces seules cases donnait un
# écart-type de 0,57 — la moitié du rayon entre 8,5 et 9,1 — parce qu'il ne
# mesurait pas la protection de la botte mais la LONGUEUR de la description :
# une fiche bavarde gagnait sur une fiche laconique, à botte identique.
#
# On exige donc qu'au moins un critère GRADUÉ ait répondu : une classe, un
# niveau, une matière, un poids, une norme nommée — quelque chose qui peut
# prendre plusieurs valeurs et donc départager deux articles. Les cases
# cochées restent dans le calcul, elles n'ont simplement plus le droit d'y
# être seules.
_GRADUE, _COCHE = True, False


def indice_protection(
    caracteristiques: list[dict[str, Any]], category_code: str
) -> dict[str, Any] | None:
    """L'indice de protection MotoComparo pour une fiche, ou `None` si la
    fiche n'a pas de quoi le fonder.

    Une moyenne pondérée, jamais une seule mesure : le poids d'un casque sans
    sa note SHARP ne dit rien de sa protection, et inversement une note SHARP
    seule ignore un casque anormalement lourd pour sa catégorie. Les
    composantes absentes sortent du calcul ET de son poids — comparer cinq
    critères à trois n'a de sens que si les poids des trois restants
    retrouvent un total de 1.

    Chaque composante est marquée `independante` quand elle vient d'un essai
    de laboratoire ou d'une norme européenne, et non de la description d'un
    vendeur, et `gradue` quand elle peut prendre plusieurs valeurs — voir
    `_GRADUE`. Le résultat repart avec ces informations : ce sont elles qui
    permettent à la page de distinguer un indice adossé à SHARP d'un indice
    bâti sur des cases cochées, au lieu d'afficher deux chiffres qui se
    ressemblent.
    """
    par_nom = {c["nom"]: c["valeur"] for c in caracteristiques}
    lire = par_nom.get
    nombre = lambda nom: _valeur_numerique(nom, lire(nom) or "")  # noqa: E731
    racine = (category_code or "").split(".", 1)[0]

    # (libellé, note sur 10 ou None, poids, essai ou norme, gradué)
    composantes: list[tuple[str, float | None, float, bool, bool]] = []

    if racine == "helmet":
        composantes = [
            ("Note SHARP", _echelonne(nombre("note_securite"), 0, 5), 0.45, True, _GRADUE),
            # Le poids PESÉ par SHARP quand il y est, celui du revendeur sinon :
            # `caracteristiques()` a déjà tranché la source en amont, ici on ne
            # revoit pas ce choix.
            ("Poids", _echelonne(nombre("poids_g"), 1900, 1250), 0.15, True, _GRADUE),
            ("Matière de calotte", _CALOTTE_VERS_NOTE.get((lire("calotte") or "").lower()),
             0.15, False, _GRADUE),
            # 22.06 impose l'essai de choc rotationnel et le test à basse
            # vitesse que 22.05 ne prévoyait pas : l'écart entre les deux
            # normes est réel, pas une date sur une étiquette.
            ("Homologation", _echelonne(nombre("homologation"), 22.05, 22.06), 0.15, True, _GRADUE),
            # Plusieurs tailles de coque = une calotte à la taille de la tête
            # plutôt qu'un rembourrage plus épais dans la même coque.
            ("Tailles de coque", _echelonne(nombre("nombre_coques"), 1, 3), 0.10, False, _GRADUE),
        ]
        base = "l'essai indépendant SHARP" if "note_securite" in par_nom else None
    elif racine in ("jacket", "suit"):
        classe = _classe_en17092(lire("classe_protection"), lire("homologation"))
        composantes = [
            ("Classe EN 17092", classe, 0.40, True, _GRADUE),
            # Seulement quand la classe manque : sinon on compterait deux fois
            # la même certification, une fois pour son niveau et une fois pour
            # son existence.
            ("Certifié EN 17092",
             _certifie(lire("norme_en17092")) if classe is None else None, 0.20, True, _COCHE),
            ("Protection dorsale", _equipement_vers_note(lire("dorsale")), 0.25, False, _GRADUE),
            ("Protections épaules/coudes", _moyenne(
                _equipement_vers_note(lire("protections_epaules")),
                _equipement_vers_note(lire("protections_coudes"))), 0.25, False, _GRADUE),
            ("Poche à dorsale", _equipement_vers_note(lire("poche_dorsale"), plafond=6.0),
             0.10, False, _COCHE),
        ]
        base = ("la classe EN 17092" if classe is not None
                else "la certification EN 17092" if lire("norme_en17092") else None)
    elif racine == "pants":
        composantes = [
            ("Niveau EN 1621-1", _moyenne(
                _echelonne(nombre("niveau_genoux"), 0, 2),
                _echelonne(nombre("niveau_hanches"), 0, 2)), 0.35, True, _GRADUE),
            ("Coques genoux", _equipement_vers_note(lire("coques_genoux")), 0.25, False, _GRADUE),
            ("Coques hanches", _equipement_vers_note(lire("coques_hanches"), plafond=9.0),
             0.20, False, _GRADUE),
            ("Renfort aramide", _equipement_vers_note(lire("renfort_aramide")), 0.20, False, _COCHE),
        ]
        base = ("les niveaux EN 1621-1"
                if "niveau_genoux" in par_nom or "niveau_hanches" in par_nom else None)
    elif racine == "gloves":
        niveau = _echelonne(nombre("niveau"), 0, 2)
        homologation = _homologation_nommee(lire("homologation"), "13594")
        # Le critère mesuré domine, et de loin. Une première répartition lui
        # donnait 0,35 contre 0,55 aux quatre cases cochées : le niveau EN,
        # seule donnée qui distingue vraiment deux gants, y pesait moins que
        # la somme de ce que tout le monde annonce. Écart-type tombé à 0,88,
        # soit un rayon entier tassé autour de 7,5.
        composantes = [
            ("Niveau EN 13594", niveau, 0.50, True, _GRADUE),
            ("Homologation", homologation if niveau is None else None, 0.40, True, _GRADUE),
            ("Coque de protection", _equipement_vers_note(lire("coque_articulations")),
             0.15, False, _COCHE),
            ("Protection articulations (KP)", _equipement_vers_note(lire("kp")), 0.10, False, _COCHE),
            ("Protection du scaphoïde", _equipement_vers_note(lire("protection_scaphoide")),
             0.05, False, _COCHE),
            ("Renfort de paume", _equipement_vers_note(lire("renfort_paume"), plafond=8.0),
             0.05, False, _COCHE),
        ]
        base = ("le niveau EN 13594" if niveau is not None
                else "l'homologation déclarée" if homologation is not None else None)
    elif racine == "boots":
        indices = _moyenne(*[
            _echelonne(nombre(n), 0, 2) for n in
            ("indice_hauteur", "indice_abrasion", "indice_coupure", "indice_rigidite")])
        homologation = _homologation_nommee(lire("homologation"), "13634")
        composantes = [
            ("Indices EN 13634", indices, 0.50, True, _GRADUE),
            # Le seul critère gradué que ce rayon fournit en nombre : la norme
            # nommée contre un « CE » générique. Sans lui, l'indice des bottes
            # ne reposait que sur des cases jamais décochées. Il domine donc,
            # pour la même raison que chez les gants.
            ("Homologation", homologation if indices is None else None, 0.45, True, _GRADUE),
            # La malléole est l'os qui casse en premier quand un pied reste
            # coincé sous la moto : c'est la protection qui distingue une
            # botte moto d'une chaussure montante, et elle pèse en conséquence.
            ("Protection de malléole", _equipement_vers_note(lire("protection_malleole")),
             0.20, False, _COCHE),
            ("Coque au bout du pied", _equipement_vers_note(lire("coque_bout_de_pied"), plafond=9.0),
             0.10, False, _COCHE),
            ("Protection du tibia", _equipement_vers_note(lire("protection_tibia"), plafond=9.0),
             0.10, False, _COCHE),
            ("Protection de sélecteur", _equipement_vers_note(lire("protection_selecteur"), plafond=7.0),
             0.05, False, _COCHE),
        ]
        base = ("la norme EN 13634" if indices is not None
                else "l'homologation déclarée" if homologation is not None else None)
    else:
        return None

    presentes = [c for c in composantes if c[1] is not None]
    if len(presentes) < _CRITERES_MINIMUM:
        return None
    if not any(gradue for _, _, _, _, gradue in presentes):
        return None   # voir le garde-fou 3 : des cases cochées ne classent rien
    poids_total = sum(poids for _, _, poids, _, _ in presentes)
    note = sum(n * poids for _, n, poids, _, _ in presentes) / poids_total
    return {
        "note": round(note, 1),
        "criteres": len(presentes),
        # `base` ne vaut quelque chose que si la norme correspondante est
        # VRAIMENT là : sans elle, la page doit dire que l'indice repose sur
        # ce que les marchands déclarent, et pas laisser croire à un essai.
        "base": base or "les caractéristiques déclarées par les marchands",
        "independante": any(ind for _, _, _, ind, _ in presentes),
        "detail": [(libelle, round(n, 1)) for libelle, n, _, _, _ in presentes],
    }


# --- l'équipement : ce que l'article sait faire en plus de protéger --------
#
# La liste par rayon est une GRILLE, pas un inventaire : elle énumère ce qu'un
# article de ce rayon peut offrir, et la note dit quelle part en est
# CONFIRMÉE. Le mot compte. Une ventilation qu'aucun marchand ne mentionne
# n'est pas une ventilation absente — c'est une ventilation dont on ne sait
# rien, et la page le dit en affichant « 3 sur 5 confirmés » à côté du
# chiffre plutôt qu'un score nu qui ferait passer un silence pour un défaut.
#
# Chaque entrée accepte plusieurs noms : le même équipement s'appelle
# `ventilation` dans un rayon et `ventilations` dans un autre, et c'est
# l'extracteur du rayon qui a tranché, pas nous.
_EQUIPEMENTS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "helmet": [
        ("Ventilation", ("ventilation",)),
        ("Pinlock", ("pinlock",)),
        ("Écran solaire", ("ecran_solaire",)),
        ("Intérieur amovible", ("interieur_amovible",)),
        ("Intercom", ("intercom",)),
    ],
    "jacket": [
        ("Membrane imperméable", ("membrane", "impermeable")),
        ("Doublure thermique", ("doublure_thermique",)),
        ("Doublure amovible", ("doublure_thermique_amovible",)),
        ("Ventilation", ("ventilations", "ventilation")),
        ("Éléments réfléchissants", ("elements_reflechissants", "reflechissants")),
        ("Zip de liaison pantalon", ("zip_liaison_pantalon",)),
        ("Réglages de serrage", ("reglages_serrage",)),
    ],
    "pants": [
        ("Membrane imperméable", ("membrane", "impermeable")),
        ("Doublure thermique", ("doublure_thermique",)),
        ("Ventilation", ("ventilation",)),
        ("Éléments réfléchissants", ("reflechissant", "reflechissants")),
        ("Zip de liaison veste", ("zip_liaison",)),
        ("Genouillères réglables", ("genouilleres_reglables",)),
    ],
    "gloves": [
        ("Compatible écran tactile", ("tactile",)),
        ("Imperméable", ("impermeable", "membrane")),
        ("Ventilation", ("ventilation",)),
        ("Doublure thermique", ("doublure_thermique",)),
        ("Chauffant", ("chauffant",)),
    ],
    "boots": [
        ("Imperméable", ("impermeable", "membrane")),
        ("Ventilation", ("ventilation",)),
        ("Éléments réfléchissants", ("reflechissants", "reflechissant")),
        ("Semelle antidérapante", ("semelle_antiderapante",)),
        ("Semelle anti-huile", ("semelle_anti_huile",)),
    ],
}
_EQUIPEMENTS["suit"] = _EQUIPEMENTS["jacket"]


def note_equipement(
    caracteristiques: list[dict[str, Any]], category_code: str
) -> dict[str, Any] | None:
    """Ce que l'article offre en plus de protéger, sur 10.

    La note est la moyenne de la grille ENTIÈRE du rayon, pas des seules
    lignes renseignées : un blouson dont on ne sait rien n'a pas « 10/10
    d'équipement » parce que son unique ligne connue dit oui. Un équipement
    seulement PRÉPARÉ — un logement d'intercom, une fixation de Pinlock — ne
    vaut pas un équipement fourni, et `_equipement_vers_note` fait déjà cette
    différence.
    """
    grille = _EQUIPEMENTS.get((category_code or "").split(".", 1)[0])
    if not grille:
        return None
    par_nom = {c["nom"]: c["valeur"] for c in caracteristiques}

    notes: list[float] = []
    confirmes: list[str] = []
    for libelle, noms in grille:
        valeur = next((par_nom[n] for n in noms if n in par_nom), None)
        note = _equipement_vers_note(valeur) if valeur else None
        if note is None and valeur:
            # Une valeur qu'on ne sait pas noter reste une PRÉSENCE : « gore-tex »
            # ou « drystar » dans `membrane` nomme une membrane, donc il y en a une.
            note = 10.0
        notes.append(note if note is not None else 0.0)
        if note:
            confirmes.append(libelle)

    if not confirmes:
        return None
    # DE 5 À 10, PAS DE 0 À 10 — et c'est la même règle que partout ailleurs
    # ici : ce qu'on ignore ne se compte pas contre l'article. Sur une échelle
    # partant de zéro, un casque dont un seul marchand laconique parle
    # tombait à 4,8 sur l'équipement et perdait un point et demi de note
    # d'ensemble, non parce qu'il est moins équipé mais parce qu'on en a moins
    # dit. L'équipement confirmé ne peut donc que faire MONTER la note ; son
    # silence la laisse au milieu.
    acquis = sum(notes) / (10.0 * len(grille))
    return {
        "note": round(5.0 + 5.0 * acquis, 1),
        "confirmes": len(confirmes),
        "total": len(grille),
        "detail": confirmes,
    }


# Ce que pèse chaque volet dans la note.
#
# La protection domine, et ce n'est pas une opinion : ces articles existent
# pour amortir un choc, et un blouson qui le fait mal reste un mauvais
# blouson même à dix euros. L'équipement suit, à moitié moins, parce qu'il
# décrit le confort plus que la sécurité.
#
# LE PRIX N'Y EST PLUS, et il n'y sera pas. Il y est entré le temps d'une
# version, pour un quart, sous la forme d'un rapport qualité-prix. Retiré à
# la demande de la propriétaire, et l'essai lui a donné raison : noter un
# article par ce qu'il coûte revient à re-trier par prix, ce que le tableau
# fait déjà, mieux, et sans prétendre juger. Le prix reste AFFICHÉ en tête de
# colonne, où il se compare d'un coup d'œil.
_POIDS_QUALITE = {"protection": 0.50, "equipement": 0.25}


def note_globale(
    caracteristiques: list[dict[str, Any]], category_code: str,
) -> dict[str, Any] | None:
    """La note MotoComparo d'une fiche : ce que l'article protège et ce qu'il
    offre, en un chiffre, et les sous-notes qui le composent.

    Le chiffre ne remplace pas ses composantes, il les résume : la page les
    affiche en dessous, parce qu'un acheteur qui cherche la protection
    maximale et un acheteur qui cherche l'équipement le plus complet ne
    lisent pas la même ligne — et qu'une note unique qui prétendrait trancher
    pour eux serait une note qui ment à l'un des deux.
    """
    protection = indice_protection(caracteristiques, category_code)
    equipement = note_equipement(caracteristiques, category_code)

    # 1. CE QUE VAUT L'ARTICLE, prix mis de côté. Les volets absents sortent
    #    du calcul ET de son poids : comparer deux volets à un seul n'a de
    #    sens que si les poids du survivant retrouvent un total de 1.
    qualites = [(libelle, note, cle) for libelle, note, cle in (
        ("Protection", protection["note"] if protection else None, "protection"),
        ("Équipement", equipement["note"] if equipement else None, "equipement"),
    ) if note is not None]
    if not qualites:
        return None   # sans rien savoir de l'article, le prix ne note rien
    poids_total = sum(_POIDS_QUALITE[cle] for _, _, cle in qualites)
    qualite = sum(n * _POIDS_QUALITE[cle] for _, n, cle in qualites) / poids_total

    # 2. LE PRIX N'ENTRE PAS DANS LA NOTE, et c'est une décision.
    #
    # Il y est entré le temps d'une version, pour un quart. Retiré à la
    # demande de la propriétaire, et l'essai a donné raison à la demande :
    # noter un article par ce qu'il coûte revient à re-trier par prix — ce
    # que le tableau fait déjà, mieux, et sans prétendre juger. Le prix reste
    # AFFICHÉ en tête de colonne, où il se compare d'un coup d'œil ; la note
    # dit ce que l'article EST, pas ce qu'il vaut à ce tarif.
    note = qualite
    volets = [(libelle, n) for libelle, n, _ in qualites]
    return {
        "note": round(note, 1),
        "volets": volets,
        "protection": protection,
        "equipement": equipement,
        # Ce qui distingue une note adossée à un essai ou à une norme d'une
        # note bâtie sur des descriptions marchandes. Voir le gabarit.
        "independante": bool(protection and protection["independante"]),
    }
