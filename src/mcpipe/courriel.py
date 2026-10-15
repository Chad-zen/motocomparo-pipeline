"""L'envoi d'un e-mail, en un seul endroit — pour le site ET pour le pipeline.

Deux usages aujourd'hui : la notification d'un message de contact (site) et les
alertes de baisse de prix (site pour la confirmation, `mcpipe alertes` la
nuit). Le code SMTP vivait dans `mcsite/app.py`, à l'intérieur de la
notification de contact ; le pipeline ne pouvait pas s'en servir sans importer
toute l'application web. Il est ici, dans `mcpipe`, parce que `mcsite` dépend
déjà de `mcpipe` et jamais l'inverse.

Hostinger Mail, SSL implicite sur le port 465, une seule boîte qui envoie.
Configuration lue dans l'environnement À CHAQUE APPEL, pas à l'import : un test
qui change une variable doit être vu, et un `.env` complété sur le serveur l'est
au prochain redémarrage sans autre geste.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

_log = logging.getLogger("mcpipe.courriel")


def configure() -> bool:
    """Vrai seulement si un envoi a une chance d'aboutir : hôte, compte ET mot
    de passe renseignés.

    C'est l'interrupteur des alertes de prix. Tant qu'il est faux — c'est le cas
    en production tant que `SMTP_PASS` est vide — le formulaire n'est PAS
    affiché : un visiteur qui s'inscrirait n'aurait jamais l'e-mail de
    confirmation, et croirait suivre un prix que personne ne surveille pour lui.
    """
    return all(os.environ.get(k, "").strip()
               for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"))


def expediteur() -> str:
    return os.environ.get("SMTP_USER", "").strip()


def envoyer(destinataire: str, sujet: str, corps: str, *,
            repondre_a: str = "", entetes: dict[str, str] | None = None,
            delai: float = 8) -> bool:
    """Envoie un e-mail texte. Rend True s'il est parti, False sinon.

    NE LÈVE JAMAIS. Les deux appelants ont déjà fait l'essentiel avant
    d'appeler (le message est en base, l'alerte est enregistrée) : un serveur
    injoignable ou un mot de passe faux ne doit coûter qu'un e-mail manqué,
    jamais la page du visiteur ni la chaîne de nuit.

    Texte seul, sans HTML : pas d'image distante, donc aucun pixel de suivi
    possible, et rien qu'un filtre anti-spam trouve suspect.

    `delai` court par défaut : côté site, le visiteur attend la réponse.
    """
    if not configure() or not destinataire:
        return False
    hote = os.environ.get("SMTP_HOST", "").strip()
    utilisateur = expediteur()
    mdp = os.environ.get("SMTP_PASS", "").strip()
    port = int(os.environ.get("SMTP_PORT", "465") or "465")

    msg = EmailMessage()
    msg["Subject"] = sujet
    msg["From"] = f"MotoComparo <{utilisateur}>"
    msg["To"] = destinataire
    if repondre_a:
        msg["Reply-To"] = repondre_a
    for nom, valeur in (entetes or {}).items():
        msg[nom] = valeur
    msg.set_content(corps)
    try:
        with smtplib.SMTP_SSL(hote, port, timeout=delai,
                              context=ssl.create_default_context()) as serveur:
            serveur.login(utilisateur, mdp)
            serveur.send_message(msg)
        return True
    except Exception:  # noqa: BLE001 — un e-mail manqué n'est pas une panne
        _log.exception("e-mail non envoyé (%s)", sujet)
        return False
