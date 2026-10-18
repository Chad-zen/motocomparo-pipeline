"""La cle d'un flux n'apparait dans aucun message d'erreur ni journal (18/10/2026)."""

from mcpipe.feeds import masquer_secrets

_CLE = "4e6caf47ebf2b8f1f2ae471dd82dd06d"
_URL = f"https://productdata.awin.com/datafeed/download/apikey/{_CLE}/language/fr/fid/1/columns/a,b/format/csv/"


def test_la_cle_awin_disparait_meme_sans_variable_d_environnement(monkeypatch):
    monkeypatch.delenv("FEED_MOTARDBLEU_URL", raising=False)
    msg = f"Client error '404 Not Found' for url '{_URL}'"
    sortie = masquer_secrets(msg)
    assert _CLE not in sortie
    assert "apikey/***" in sortie
    assert "404 Not Found" in sortie  # le reste du message reste lisible


def test_l_url_exacte_de_l_environnement_est_remplacee(monkeypatch):
    monkeypatch.setenv("FEED_UNTEL_URL", "https://exemple.test/flux?id=7")
    assert "exemple.test" not in masquer_secrets("echec sur https://exemple.test/flux?id=7")


def test_un_jeton_d_environnement_est_masque(monkeypatch):
    monkeypatch.setenv("FEED_UNTEL_TOKEN", "s3cr3t-jeton")
    assert "s3cr3t-jeton" not in masquer_secrets("Bearer s3cr3t-jeton refuse")


def test_parametres_secrets_dans_une_url():
    sortie = masquer_secrets("GET https://x.test/f?token=abc123&page=2")
    assert "abc123" not in sortie and "page=2" in sortie


def test_un_message_sans_secret_est_inchange():
    assert masquer_secrets("connexion refusee") == "connexion refusee"
