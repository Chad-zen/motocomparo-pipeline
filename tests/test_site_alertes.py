"""Les alertes de baisse de prix.

Quatre choses à garantir, et c'est le plan du fichier :

1. le formulaire de la fiche est INVISIBLE tant que l'envoi d'e-mails n'est
   pas configuré (`SMTP_PASS` vide en production au 15/10/2026) — montrer un
   bouton qui ne peut aboutir à rien tromperait le visiteur ;
2. le double consentement : rien n'est envoyé avant que le lien reçu par
   e-mail ait été ouvert ET confirmé ;
3. la désinscription, en un clic et par formulaire ;
4. la règle de nuit (`mcpipe.alertes.a_prevenir`) : une baisse déclenche un
   e-mail, l'absence de baisse n'en déclenche aucun, la taille est respectée,
   et une alerte déjà prévenue ne repart que sur une baisse SUPPLÉMENTAIRE.

Aucun test ici ne contacte un vrai serveur SMTP : `mcpipe.courriel.envoyer`
est toujours remplacé par un faux, qui note ce qu'il aurait envoyé.
"""

from __future__ import annotations

import os
import re

import pytest

from mcpipe.alertes import a_prevenir, meilleure, taille_correspond

# Les tests qui ouvrent le site ont besoin de la base ; voir la fixture
# `client` ci-dessous. Les tests de règle pure (section 4) n'en ont pas besoin
# et tournent toujours.


# --- 4. la règle de nuit, sans base ni réseau -----------------------------------

def _offre(prix, size_code=None):
    return {"price": prix, "size_code": size_code}


def test_taille_correspond_etiquette_simple():
    assert taille_correspond("M", "M")
    assert not taille_correspond("M", "L")


def test_taille_correspond_fusion_barcode():
    """`XS / 6` couvre les deux noms que les marchands donnent à la même
    taille (voir `labels.equivalences_tailles`)."""
    assert taille_correspond("XS / 6", "6")
    assert taille_correspond("XS / 6", "XS")
    assert not taille_correspond("XS / 6", "M")


def test_taille_correspond_aucune_taille_demandee():
    assert taille_correspond(None, "M")
    assert taille_correspond("", "M")


def test_taille_correspond_offre_sans_taille_lisible():
    """Une offre dont on ne connaît pas la taille ne vaut pas pour UNE taille
    précise : l'alerte ne doit pas promettre un M sur un article peut-être XL."""
    assert not taille_correspond("M", None)
    assert not taille_correspond("M", "TU")


def test_meilleure_filtre_par_taille():
    offres = [_offre(100, "M"), _offre(50, "L"), _offre(80, "M")]
    assert meilleure(offres, "M")["price"] == 80
    assert meilleure(offres, None)["price"] == 50
    assert meilleure(offres, "XL") is None


def test_baisse_sous_la_reference_declenche():
    alerte = {"taille": None, "prix_cible": None, "prix_reference": 100,
              "dernier_prix_notifie": None}
    o = a_prevenir(alerte, [_offre(89.90)])
    assert o is not None and o["price"] == 89.90


def test_absence_de_baisse_ne_declenche_rien():
    alerte = {"taille": None, "prix_cible": None, "prix_reference": 100,
              "dernier_prix_notifie": None}
    assert a_prevenir(alerte, [_offre(100)]) is None
    assert a_prevenir(alerte, [_offre(120)]) is None


def test_prix_cible_atteint_declenche_meme_sans_baisse_recente():
    alerte = {"taille": None, "prix_cible": 90, "prix_reference": 150,
              "dernier_prix_notifie": None}
    assert a_prevenir(alerte, [_offre(90)]) is not None
    assert a_prevenir(alerte, [_offre(95)]) is None


def test_taille_demandee_ignore_les_offres_des_autres_tailles():
    alerte = {"taille": "M", "prix_cible": None, "prix_reference": 100,
              "dernier_prix_notifie": None}
    # 50 € existe, mais en L : ne doit pas déclencher une alerte posée sur M.
    assert a_prevenir(alerte, [_offre(50, "L"), _offre(95, "M")]) is not None
    assert a_prevenir(alerte, [_offre(50, "L")]) is None


def test_deja_notifie_ne_repart_pas_au_meme_prix():
    alerte = {"taille": None, "prix_cible": None, "prix_reference": 100,
              "dernier_prix_notifie": 80}
    assert a_prevenir(alerte, [_offre(80)]) is None
    assert a_prevenir(alerte, [_offre(85)]) is None  # remonté : toujours rien


def test_nouvelle_baisse_sous_le_dernier_prix_notifie_repart():
    alerte = {"taille": None, "prix_cible": None, "prix_reference": 100,
              "dernier_prix_notifie": 80}
    o = a_prevenir(alerte, [_offre(69.90)])
    assert o is not None and o["price"] == 69.90


def test_aucune_offre_achetable_ne_declenche_rien():
    alerte = {"taille": None, "prix_cible": None, "prix_reference": 100,
              "dernier_prix_notifie": None}
    assert a_prevenir(alerte, []) is None


# --- 1., 2., 3. : le site, avec la base --------------------------------------

EMAIL_TEST = "test-alertes@exemple.invalid"


@pytest.fixture(scope="module")
def client():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("le site a besoin de la base")
    from fastapi.testclient import TestClient

    from mcsite.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def une_fiche_avec_prix(client):
    """Un slug réel, avec un prix affiché — pris dans l'accueil, comme
    `test_site_pages.une_fiche` : en écrire un en dur ferait passer le test au
    vert le jour où le pipeline le renomme."""
    m = re.search(r'href="/p/([^"]+)"', client.get("/").text)
    if not m:
        pytest.skip("aucune fiche sur l'accueil")
    return m.group(1)


@pytest.fixture(autouse=True)
def _nettoyer_alertes_de_test():
    """Efface toute trace laissée par ces tests, avant et après : une adresse
    de test ne doit jamais persister dans la base de développement, et un test
    précédent interrompu ne doit pas fausser les plafonds du suivant."""
    def _purge():
        if not os.environ.get("DATABASE_URL"):
            return
        from mcpipe.db import connect
        conn = connect()
        conn.execute("DELETE FROM alerte_prix WHERE email = %s", (EMAIL_TEST,))
        conn.commit()
        conn.close()
    _purge()
    yield
    _purge()


def _sans_smtp(monkeypatch):
    for cle in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"):
        monkeypatch.delenv(cle, raising=False)


def _avec_smtp(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.exemple.invalide")
    monkeypatch.setenv("SMTP_USER", "contact@motocomparo.com")
    monkeypatch.setenv("SMTP_PASS", "peu-importe")


def test_formulaire_absent_sans_smtp(client, une_fiche_avec_prix, monkeypatch):
    _sans_smtp(monkeypatch)
    page = client.get(f"/p/{une_fiche_avec_prix}").text
    assert "Prévenez-moi si le prix baisse" not in page
    assert 'action="/alertes"' not in page


def test_formulaire_present_avec_smtp(client, une_fiche_avec_prix, monkeypatch):
    _avec_smtp(monkeypatch)
    page = client.get(f"/p/{une_fiche_avec_prix}").text
    assert "Prévenez-moi si le prix baisse" in page
    assert 'action="/alertes"' in page


def test_route_alertes_404_sans_smtp(client, une_fiche_avec_prix, monkeypatch):
    """Un envoi fabriqué à la main ne doit pas pouvoir enregistrer une adresse
    à qui l'on ne pourrait jamais écrire la confirmation."""
    _sans_smtp(monkeypatch)
    r = client.post("/alertes", data={"produit": une_fiche_avec_prix,
                                      "email": EMAIL_TEST}, follow_redirects=False)
    assert r.status_code == 404


def test_infos_tait_les_alertes_sans_smtp(client, monkeypatch):
    _sans_smtp(monkeypatch)
    page = client.get("/infos").text
    assert "Alerte de baisse de prix" not in page


def test_infos_decrit_les_alertes_avec_smtp(client, monkeypatch):
    _avec_smtp(monkeypatch)
    page = client.get("/infos").text
    assert "Alerte de baisse de prix" in page
    assert "6" in page and "mois" in page


def test_double_opt_in_rien_n_est_envoye_avant_confirmation(
        client, une_fiche_avec_prix, monkeypatch):
    """Le cœur du RGPD ici : la demande s'enregistre NON confirmée, un seul
    e-mail (la confirmation) part, et aucune ligne n'est « active » avant le
    clic sur le lien."""
    _avec_smtp(monkeypatch)
    envoyes = []

    def _faux_envoi(destinataire, sujet, corps, **kw):
        envoyes.append((destinataire, sujet, corps))
        return True

    monkeypatch.setattr("mcpipe.courriel.envoyer", _faux_envoi)

    r = client.post("/alertes", data={"produit": une_fiche_avec_prix,
                                      "email": EMAIL_TEST},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/alertes/demande")

    assert len(envoyes) == 1
    dest, sujet, corps = envoyes[0]
    assert dest == EMAIL_TEST
    assert "Confirmez votre alerte" in sujet
    m = re.search(r"jeton=([A-Za-z0-9_-]+)", corps)
    assert m, "le lien de confirmation doit porter un jeton"
    jeton = m.group(1)

    from mcpipe.db import connect
    conn = connect()
    ligne = conn.execute(
        "SELECT confirme_le FROM alerte_prix WHERE jeton = %s", (jeton,)).fetchone()
    conn.close()
    assert ligne is not None
    assert ligne[0] is None, "non confirmée : confirme_le doit rester NULL"

    # La page de confirmation affiche un bouton, elle ne confirme pas d'elle-même.
    page = client.get(f"/alertes/confirmer?jeton={jeton}").text
    assert "Confirmer l'alerte" in page
    conn = connect()
    ligne = conn.execute(
        "SELECT confirme_le FROM alerte_prix WHERE jeton = %s", (jeton,)).fetchone()
    conn.close()
    assert ligne[0] is None, "un GET seul ne doit jamais confirmer"

    r = client.post("/alertes/confirmer", data={"jeton": jeton})
    assert "Alerte activée" in r.text
    conn = connect()
    ligne = conn.execute(
        "SELECT confirme_le FROM alerte_prix WHERE jeton = %s", (jeton,)).fetchone()
    conn.close()
    assert ligne[0] is not None, "confirmée après le POST"


def test_reponse_identique_adresse_connue_ou_pas(client, une_fiche_avec_prix,
                                                 monkeypatch):
    """Ne jamais révéler si une adresse est déjà inscrite."""
    _avec_smtp(monkeypatch)
    monkeypatch.setattr("mcpipe.courriel.envoyer", lambda *a, **k: True)
    r1 = client.post("/alertes", data={"produit": une_fiche_avec_prix,
                                       "email": EMAIL_TEST}, follow_redirects=False)
    r2 = client.post("/alertes", data={"produit": une_fiche_avec_prix,
                                       "email": EMAIL_TEST}, follow_redirects=False)
    assert r1.status_code == r2.status_code == 303
    assert r1.headers["location"] == r2.headers["location"]


def test_champ_piege_rempli_n_enregistre_rien(client, une_fiche_avec_prix,
                                               monkeypatch):
    _avec_smtp(monkeypatch)
    appels = []
    monkeypatch.setattr("mcpipe.courriel.envoyer",
                        lambda *a, **k: appels.append(1) or True)
    client.post("/alertes", data={"produit": une_fiche_avec_prix,
                                  "email": EMAIL_TEST, "site_web": "http://spam"},
               follow_redirects=False)
    assert not appels
    from mcpipe.db import connect
    conn = connect()
    n = conn.execute("SELECT count(*) FROM alerte_prix WHERE email = %s",
                     (EMAIL_TEST,)).fetchone()[0]
    conn.close()
    assert n == 0


def test_desinscription_en_un_clic_efface_la_ligne(client, une_fiche_avec_prix,
                                                    monkeypatch):
    _avec_smtp(monkeypatch)
    monkeypatch.setattr("mcpipe.courriel.envoyer", lambda *a, **k: True)
    from mcpipe.db import connect
    conn = connect()
    conn.execute(
        "INSERT INTO alerte_prix (email, produit_slug, jeton, confirme_le) "
        "VALUES (%s, %s, %s, now())",
        (EMAIL_TEST, une_fiche_avec_prix, "jeton-desinscription-test-0001"))
    conn.commit()
    conn.close()

    r = client.get("/alertes/arreter?jeton=jeton-desinscription-test-0001")
    assert "Alerte arrêtée" in r.text

    conn = connect()
    n = conn.execute("SELECT count(*) FROM alerte_prix WHERE jeton = %s",
                     ("jeton-desinscription-test-0001",)).fetchone()[0]
    conn.close()
    assert n == 0


def test_tout_supprimer_efface_toutes_les_alertes_de_l_adresse(
        client, une_fiche_avec_prix, monkeypatch):
    _avec_smtp(monkeypatch)
    from mcpipe.db import connect
    conn = connect()
    conn.execute(
        "INSERT INTO alerte_prix (email, produit_slug, taille, jeton, confirme_le) "
        "VALUES (%s, %s, NULL, %s, now()), (%s, %s, 'M', %s, now())",
        (EMAIL_TEST, une_fiche_avec_prix, "jeton-tout-supprimer-test-aaaa",
         EMAIL_TEST, une_fiche_avec_prix, "jeton-tout-supprimer-test-bbbb"))
    conn.commit()
    conn.close()

    page = client.get("/alertes/tout-supprimer?jeton=jeton-tout-supprimer-test-aaaa").text
    assert "2 alerte" in page

    r = client.post("/alertes/tout-supprimer",
                    data={"jeton": "jeton-tout-supprimer-test-aaaa"})
    assert "effacées" in r.text

    conn = connect()
    n = conn.execute("SELECT count(*) FROM alerte_prix WHERE email = %s",
                     (EMAIL_TEST,)).fetchone()[0]
    conn.close()
    assert n == 0


def test_jeton_inconnu_ne_casse_rien(client):
    assert "Lien expiré" in client.get("/alertes/confirmer?jeton=nimportequoi").text
    assert "Lien expiré" in client.get("/alertes/arreter?jeton=nimportequoi").text


# --- le passage de nuit, de bout en bout, contre la vraie base --------------

def test_run_alertes_bout_en_bout_rejouable(client, une_fiche_avec_prix, monkeypatch):
    """Une alerte confirmée, dont le prix du jour est sous la référence,
    reçoit UN e-mail au premier passage de `mcpipe alertes` et AUCUN au
    second — c'est ce qui rend la commande de nuit rejouable sans risque.

    `last_seen` d'une vraie offre liée est avancé à `now()` pour la durée du
    test (la base de développement peut être vieille de plusieurs jours, donc
    hors de la fenêtre `_FRESH` de 24 h) puis restauré — aucune autre donnée
    n'est inventée.
    """
    from mcpipe.alertes import offres_achetables, run_alertes
    from mcpipe.db import connect

    conn = connect()
    offre = conn.execute("""
        SELECT o.id, o.last_seen FROM raw_offer o
        JOIN product p ON p.id = o.product_id
        JOIN merchant m ON m.id = o.merchant_id AND m.affiche
        WHERE p.slug = %s AND o.linked_status = 'linked' AND o.price IS NOT NULL
          AND o.in_stock IS NOT FALSE
        ORDER BY o.price LIMIT 1
    """, (une_fiche_avec_prix,)).fetchone()
    if offre is None:
        conn.close()
        pytest.skip("aucune offre achetable pour cette fiche")
    offre_id, last_seen_original = offre
    conn.execute("UPDATE raw_offer SET last_seen = now() WHERE id = %s", (offre_id,))
    conn.commit()
    try:
        offres = offres_achetables(conn, [une_fiche_avec_prix])[une_fiche_avec_prix]
        assert offres, "l'offre avancée doit maintenant compter comme fraîche"
        prix_du_jour = min(o["price"] for o in offres)

        conn.execute(
            "INSERT INTO alerte_prix (email, produit_slug, jeton, confirme_le, "
            "prix_reference) VALUES (%s, %s, %s, now(), %s)",
            (EMAIL_TEST, une_fiche_avec_prix,
             "jeton-nuit-bout-en-bout-test-0001", float(prix_du_jour) + 50))
        conn.commit()

        envoyes = []
        monkeypatch.setattr(
            "mcpipe.courriel.envoyer",
            lambda dest, sujet, corps, **k: envoyes.append(dest) or True)
        _avec_smtp(monkeypatch)

        run_alertes()
        assert envoyes == [EMAIL_TEST]

        run_alertes()  # rejoué tout de suite : rien de nouveau à annoncer
        assert envoyes == [EMAIL_TEST], (
            "un second passage sans nouvelle baisse ne doit renvoyer aucun e-mail")

        ligne = conn.execute(
            "SELECT dernier_prix_notifie FROM alerte_prix WHERE jeton = %s",
            ("jeton-nuit-bout-en-bout-test-0001",)).fetchone()
        assert ligne is not None and float(ligne[0]) == float(prix_du_jour)
    finally:
        conn.execute("UPDATE raw_offer SET last_seen = %s WHERE id = %s",
                     (last_seen_original, offre_id))
        conn.commit()
        conn.close()


def test_purge_efface_les_demandes_non_confirmees_perimees(client):
    """Une demande jamais confirmée, vieille de plus de 7 jours, est effacée ;
    une demande récente, ou confirmée, ne l'est pas."""
    from mcpipe.alertes import purger
    from mcpipe.db import connect

    conn = connect()
    conn.execute(
        "INSERT INTO alerte_prix (email, produit_slug, taille, jeton, cree_le) "
        "VALUES (%s, 'fiche-inexistante-peu-importe', 'perimee', %s, "
        "now() - interval '8 days')",
        (EMAIL_TEST, "jeton-purge-perime-test-000001"))
    conn.execute(
        "INSERT INTO alerte_prix (email, produit_slug, taille, jeton, cree_le) "
        "VALUES (%s, 'fiche-inexistante-peu-importe', 'recente', %s, "
        "now() - interval '1 day')",
        (EMAIL_TEST, "jeton-purge-recente-test-0000001"))
    conn.commit()
    purger(conn)
    conn.commit()
    restantes = {r[0] for r in conn.execute(
        "SELECT jeton FROM alerte_prix WHERE email = %s", (EMAIL_TEST,)).fetchall()}
    conn.close()
    assert "jeton-purge-perime-test-000001" not in restantes
    assert "jeton-purge-recente-test-0000001" in restantes


def test_plafond_par_adresse(client, une_fiche_avec_prix):
    """Au-delà de `MAX_PAR_ADRESSE`, une adresse ne peut plus ouvrir de
    nouvelle demande — mais la réponse au visiteur ne le dit jamais."""
    from mcpipe.alertes import MAX_PAR_ADRESSE, enregistrer_demande
    from mcpipe.db import connect

    conn = connect()
    conn.autocommit = True
    for i in range(MAX_PAR_ADRESSE):
        conn.execute(
            "INSERT INTO alerte_prix (email, produit_slug, taille, jeton, confirme_le) "
            "VALUES (%s, 'fiche-inexistante-peu-importe', %s, %s, now())",
            (EMAIL_TEST, f"taille-{i}", f"jeton-plafond-test-{i:010d}"))
    jeton = enregistrer_demande(conn, email=EMAIL_TEST,
                                slug=une_fiche_avec_prix, taille=None,
                                prix_cible=None, prix_reference=None)
    conn.close()
    assert jeton is None, "le plafond doit refuser une nouvelle demande, en silence"
