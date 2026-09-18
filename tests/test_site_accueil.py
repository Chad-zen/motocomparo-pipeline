"""Les trois rangées de l'accueil, et les règles qu'on ne voit pas à l'écran.

Ces règles sont invisibles : une rangée fausse ressemble exactement à une
rangée juste. « Ça a baissé cette semaine » remplie de baisses inventées a la
même allure que la vraie ; « Nouveautés » tirée au hasard dans tout le
catalogue aussi. D'où des tests qui vérifient la PROPRIÉTÉ — pas de doublon de
marchand, la baisse porte bien sur le prix affiché, rien du versement initial —
et jamais une liste de slugs, qui changerait à la prochaine collecte.

Ils lisent la vraie base : c'est le seul endroit où ces règles existent.
"""

from __future__ import annotations

import os

import psycopg
import pytest

from mcsite import queries

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="ces rangées se vérifient contre la vraie base")


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        yield c


@pytest.fixture(scope="module")
def casques(conn):
    return queries.find_category(queries.categories(conn), "helmet")["ids"]


# --- « Là où comparer rapporte le plus » : varié, pas maximal -----------------

def test_les_ecarts_couvrent_plusieurs_tranches(conn):
    """La consigne de la propriétaire : « pas celles qui sont le plus élevées,
    varie les baisses ». Douze fois la queue de la distribution n'apprenait rien
    à personne."""
    bandes = {r["bande"] for r in queries.ecarts(conn, 12)}
    assert len(bandes) >= 3


def test_les_ecarts_ne_descendent_pas_sous_quinze(conn):
    """Varier ne veut pas dire descendre : la bande 0 ouvrait la rangée — donc
    la page d'accueil — sur « −14 % »."""
    assert all(r["remise"] >= 15 for r in queries.ecarts(conn, 12))


def test_les_ecarts_ne_bougent_pas_dans_la_journee(conn):
    """Le tirage est arbitraire mais STABLE : un `random()` aurait changé la
    rangée à chaque expiration du cache, sous les yeux du visiteur qui revient.

    Ce test tient aussi les `DISTINCT ON` sans départage — le défaut était là
    avant, invisible tant que la rangée classait au pourcentage."""
    a = [r["slug"] for r in queries.ecarts(conn, 12, jour="2026-09-17")]
    b = [r["slug"] for r in queries.ecarts(conn, 12, jour="2026-09-17")]
    assert a == b and len(a) == 12


def test_les_ecarts_tournent_d_un_jour_a_l_autre(conn):
    """… et figée pour toujours, elle ne montrerait jamais que les mêmes douze
    fiches. Elle tourne une fois par jour."""
    a = [r["slug"] for r in queries.ecarts(conn, 12, jour="2026-09-17")]
    b = [r["slug"] for r in queries.ecarts(conn, 12, jour="2026-09-24")]
    assert a != b


# --- « Nouveautés casque » : la date qu'il faut lire --------------------------

def test_les_nouveautes_sont_du_bon_rayon(conn, casques):
    slugs = [r["slug"] for r in queries.nouveautes(conn, casques, 12)]
    if not slugs:
        pytest.skip("aucune nouveauté dans cette base")
    hors = conn.execute(
        "SELECT count(*) FROM product WHERE slug = ANY(%s) AND NOT (category_id = ANY(%s))",
        (slugs, casques)).fetchone()[0]
    assert hors == 0


def test_les_nouveautes_excluent_le_versement_initial(conn, casques):
    """`product.created_at` vaut le même jour pour les 313 435 fiches : c'est la
    date de reconstruction de la table, pas une date de nouveauté. S'en servir
    aurait donné une rangée tirée au hasard dans tout le catalogue — un mensonge
    sans même le savoir. La date lue est celle de la première offre vue, et le
    jour du versement initial ne compte pas."""
    jour = conn.execute("SELECT min(first_seen)::date FROM raw_offer").fetchone()[0]
    for r in queries.nouveautes(conn, casques, 12):
        assert r["vue_le"] > jour


def test_une_famille_vide_ne_lance_aucune_requete(conn):
    assert queries.nouveautes(conn, [], 12) == []


# --- « Ça a baissé cette semaine » : la même offre, comparée à elle-même ------

def test_la_baisse_porte_sur_le_prix_affiche(conn):
    """La comparaison qu'il ne faut pas faire : le prix mini d'il y a une
    semaine contre celui d'aujourd'hui. Un marchand moins cher qui ARRIVE aurait
    suffi à inventer une baisse. Ici `maintenant` doit être le prix que la fiche
    affiche vraiment."""
    for r in queries.baisses(conn, 12):
        affiche = conn.execute("""
            SELECT min(o.price) FROM raw_offer o JOIN product p ON p.id = o.product_id
            WHERE p.slug = %s AND o.linked_status = 'linked' AND o.is_live
              AND o.price IS NOT NULL AND o.in_stock IS NOT FALSE
        """, (r["slug"],)).fetchone()[0]
        assert r["maintenant"] == affiche


def test_aucun_marchand_ne_prend_la_rangee(conn):
    """FC-Moto a baissé 112 149 de ses 143 523 offres, La Bécanerie aucune sur
    222 907. Sans plafond dur, la queue de la rangée se remplissait du seul
    marchand qui avait encore des candidats : six places sur douze, toutes à
    −55 pile. La rangée a le droit d'être plus courte ; elle n'a pas le droit
    d'être le catalogue d'un marchand."""
    lignes = queries.baisses(conn, 12, par_marchand=3)
    for m in {r["merchant_id"] for r in lignes}:
        assert sum(1 for r in lignes if r["merchant_id"] == m) <= 3


def test_la_baisse_pese_en_euros_et_reste_credible(conn):
    """Un écran de casque qui passe de 15,00 € à 4,53 € affiche un beau
    pourcentage et ne mérite pas la page d'accueil ; au-delà de la moitié, c'est
    une erreur de flux bien plus souvent qu'une affaire."""
    for r in queries.baisses(conn, 12):
        assert r["avant"] - r["maintenant"] >= 20
        assert 10 <= r["baisse"] <= 55


def test_les_baisses_ne_bougent_pas_a_donnees_egales(conn):
    """SIX calculs, pas deux, et on compare AUSSI le marchand retenu.

    Ce test a échoué une fois puis est repassé seul — le pire symptôme qui
    soit, celui qu'on attribue à la malchance. La cause : deux marchands au
    MÊME prix sur la même fiche (le Shark OXO Rydger chez Maxxess et
    Moto-Axxe). Les deux lignes étaient identiques jusqu'au slug, PostgreSQL en
    gardait une au hasard, et comme la rangée répartit ensuite par marchand,
    les douze cartes se réorganisaient derrière.

    Deux tirages avaient une chance sur deux de tomber pareil : c'est pour ça
    que le défaut a survécu. Six tirages, et sur les deux champs qui comptent."""
    tirages = [[(r["slug"], r["merchant_id"]) for r in queries.baisses(conn, 12)]
               for _ in range(6)]
    assert len(set(map(tuple, tirages))) == 1


# --- « pas de photo, pas de place sur l'accueil » ----------------------------

def test_aucune_rangee_ne_montre_une_fiche_sans_photo(conn, casques):
    """Règle de la propriétaire, 18/09/2026.

    Une carte « pas de visuel » posée au milieu de onze photos ne se lit pas
    comme une fiche sans image : elle se lit comme un site cassé.

    Aucune fiche n'est dans ce cas aujourd'hui — 0 sur 8 221 à trois marchands —
    et c'est précisément pourquoi ce test existe. Le jour où un marchand
    retirera une photo, personne ne relancera cette mesure à la main, et rien
    dans la page ne préviendra."""
    rangees = (queries.ecarts(conn, 12)
               + queries.nouveautes(conn, casques, 12)
               + queries.baisses(conn, 12))
    assert rangees, "les trois rangées sont vides : le test ne prouverait rien"
    sans = [r["slug"] for r in rangees if not (r.get("image_url") or "").strip()]
    assert not sans, f"fiches sans photo sur l'accueil : {sans}"
