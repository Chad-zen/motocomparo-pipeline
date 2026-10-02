"""La notification par e-mail du formulaire de contact — voir `_notifier_contact`.

Rien n'est envoyé pour de vrai ici (aucun serveur SMTP en test) : ces tests
vérifient seulement qu'elle se tait proprement tant qu'elle n'est pas
configurée, et qu'une panne d'envoi ne remonte jamais jusqu'au visiteur.
"""

from mcsite.app import _notifier_contact


def test_silencieuse_sans_smtp_host(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    # Ne doit lever aucune exception, et ne rien tenter.
    _notifier_contact("autre", "un message", "visiteur@exemple.fr", "/contact")


def test_silencieuse_sans_mot_de_passe(monkeypatch):
    # L'hôte seul ne suffit pas à activer l'envoi : il faut aussi un compte.
    monkeypatch.setenv("SMTP_HOST", "smtp.hostinger.com")
    monkeypatch.setenv("SMTP_USER", "contact@motocomparo.com")
    monkeypatch.delenv("SMTP_PASS", raising=False)
    _notifier_contact("autre", "un message", "visiteur@exemple.fr", "/contact")


def test_un_echec_d_envoi_ne_remonte_jamais(monkeypatch):
    """Même configurée, une erreur réseau/SMTP reste entièrement avalée —
    c'est la garantie qui permet de l'appeler après l'écriture en base sans
    jamais risquer la page de confirmation du visiteur."""
    monkeypatch.setenv("SMTP_HOST", "smtp.invalide.exemple")
    monkeypatch.setenv("SMTP_USER", "contact@motocomparo.com")
    monkeypatch.setenv("SMTP_PASS", "peu-importe")
    monkeypatch.setenv("SMTP_PORT", "465")
    # Hôte inexistant : smtplib.SMTP_SSL doit échouer à la connexion, et
    # l'échec doit rester dans la fonction.
    _notifier_contact("erreur-prix", "un message", "", "/p/exemple")
