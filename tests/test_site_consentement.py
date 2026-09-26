"""Le consentement, et la promesse que la page Confidentialité tient.

CE QUE CES VÉRIFICATIONS PROTÈGENT. Une balise de mesure et une page qui jure
qu'il n'y en a pas sont deux fichiers différents, écrits à des moments
différents, et rien n'oblige le second à suivre le premier — sauf ceci.

La règle est simple et vaut dans les deux sens :

  * sans identifiant configuré, AUCUN script Google ne doit sortir, et la page
    Confidentialité doit pouvoir affirmer qu'il n'y a pas de mesure ;
  * avec un identifiant, le consentement par défaut doit être écrit AVANT le
    conteneur, tout doit y être refusé, et la page Confidentialité doit décrire
    la mesure au lieu de la nier.

L'ordre des deux scripts est vérifié par leur POSITION dans le HTML, pas par
leur simple présence : un `default` placé après le conteneur est syntaxiquement
correct, se charge sans erreur, et ne sert à rien. C'est précisément le genre
de panne qui ne se voit pas.
"""

from __future__ import annotations

import importlib
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="rendre une page demande la base")


def _client(monkeypatch, **env):
    """Un client dont l'application a été relue avec cet environnement.

    Les identifiants sont lus à l'import du module (`_GTM_ID`) : il faut donc
    le recharger, sans quoi on testerait la configuration de la machine qui
    lance les tests plutôt que celle qu'on veut éprouver.
    """
    from fastapi.testclient import TestClient

    for cle in ("GTM_ID", "GA4_ID"):
        monkeypatch.setenv(cle, env.get(cle, ""))
    import mcsite.app as app_module
    app_module = importlib.reload(app_module)
    return TestClient(app_module.app)


@pytest.fixture(autouse=True)
def _rendre_l_application():
    """Remet l'application dans l'état de la machine après chaque test : un
    module rechargé le reste, et le fichier suivant hériterait d'un site
    configuré par celui-ci.

    Les deux variables sont effacées AVANT le rechargement, et pas laissées à
    `monkeypatch` : son propre nettoyage passe après celui-ci, si bien que le
    test de l'identifiant fantaisiste relançait la validation avec la valeur
    fautive encore en place — et échouait dans son ménage, pas dans son sujet.
    """
    yield
    for cle in ("GTM_ID", "GA4_ID"):
        os.environ.pop(cle, None)
    import mcsite.app as app_module
    importlib.reload(app_module)


def test_sans_identifiant_aucun_script_google(monkeypatch):
    with _client(monkeypatch) as c:
        page = c.get("/").text
    assert "googletagmanager.com" not in page
    assert "gtag(" not in page
    assert 'id="consentement"' not in page, (
        "un bandeau qui n'a rien à faire consentir n'a rien à demander")


def test_sans_identifiant_la_page_confidentialite_peut_le_jurer(monkeypatch):
    with _client(monkeypatch) as c:
        page = c.get("/infos").text
    assert "ne dépose aucun cookie" in page
    assert "Google Analytics" not in page


def test_avec_identifiant_le_consentement_precede_le_conteneur(monkeypatch):
    """L'erreur la plus courante du Consent Mode, et la plus invisible."""
    with _client(monkeypatch, GTM_ID="GTM-TEST123") as c:
        page = c.get("/").text
    defaut = page.index("gtag('consent', 'default'")
    conteneur = page.index("googletagmanager.com/gtm.js")
    assert defaut < conteneur, (
        "le consentement par défaut doit être posé AVANT le conteneur, "
        "sinon les balises partent avant de savoir ce que le visiteur a choisi")


def test_avec_identifiant_tout_est_refuse_au_depart(monkeypatch):
    with _client(monkeypatch, GTM_ID="GTM-TEST123") as c:
        page = c.get("/").text
    bloc = page[page.index("gtag('consent', 'default'"):page.index("wait_for_update")]
    for etat in ("ad_storage", "ad_user_data", "ad_personalization", "analytics_storage"):
        assert f"{etat}: 'denied'" in bloc, f"{etat} doit être refusé par défaut"


def test_refuser_est_aussi_accessible_qu_accepter(monkeypatch):
    """La règle de la CNIL que les bandeaux contournent le plus souvent.

    On vérifie que les deux réponses sont de vrais boutons de la même classe :
    un « Refuser » en lien gris sous un bouton coloré est le motif sanctionné.
    """
    with _client(monkeypatch, GTM_ID="GTM-TEST123") as c:
        page = c.get("/").text
    assert 'data-consentement="refuse"' in page
    assert 'data-consentement="accepte"' in page
    refus = page.index('data-consentement="refuse"')
    accept = page.index('data-consentement="accepte"')
    assert refus < accept, "le refus se lit et s'atteint en premier"
    assert page.count('class="bouton bouton--contour" data-consentement') == 1
    assert "Gérer les cookies" in page, "le choix doit pouvoir être changé"


def test_avec_identifiant_la_page_confidentialite_decrit_la_mesure(monkeypatch):
    with _client(monkeypatch, GTM_ID="GTM-TEST123") as c:
        page = c.get("/infos").text
    assert "Google Analytics" in page
    assert "ne dépose aucun cookie" not in page, (
        "la page ne peut pas nier une mesure que le site vient d'activer")


def test_ga4_seul_se_branche_sans_conteneur(monkeypatch):
    with _client(monkeypatch, GA4_ID="G-TEST12345") as c:
        page = c.get("/").text
    assert "gtag/js?id=G-TEST12345" in page
    assert "gtm.js" not in page, "GA4 seul ne doit pas charger de conteneur"
    assert 'id="consentement"' in page


def test_un_identifiant_fantaisiste_arrete_le_site(monkeypatch):
    """Ce champ finit dans une balise `<script>` : il ne se prend pas sur
    parole. Mieux vaut un démarrage qui échoue en le disant qu'une page qui
    injecte n'importe quoi."""
    monkeypatch.setenv("GTM_ID", "<script>alert(1)</script>")
    monkeypatch.setenv("GA4_ID", "")
    import mcsite.app as app_module
    with pytest.raises(RuntimeError, match="GTM_ID"):
        importlib.reload(app_module)
