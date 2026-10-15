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
from email.utils import make_msgid
from pathlib import Path

_log = logging.getLogger("mcpipe.courriel")

# Le bandeau de marque des e-mails — casque, gants, blouson, flèche, étiquette,
# en or sur fond nuit (fournie par la propriétaire, 15/10/2026). Lu sur disque
# et JOINT au message (Content-ID) plutôt que référencé par une adresse
# distante : un e-mail ne charge donc jamais rien sur le réseau pour
# s'afficher, et son ouverture ne peut pas être mesurée par ce biais.
_BANNIERE = Path(__file__).resolve().parent.parent / "mcsite" / "static" / "email" / "alerte-banniere.png"


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


def cid_banniere() -> str:
    """Le Content-ID à écrire dans un `<img src="cid:...">` du HTML d'un
    e-mail. Toujours la même valeur, dérivée du fichier et non tirée au hasard
    (`make_msgid` change à chaque appel) : deux parties HTML du même envoi — le
    texte de confirmation et celui de la baisse — doivent pouvoir citer le
    même bandeau sans le joindre deux fois."""
    return "banniere-motocomparo"


def envoyer(destinataire: str, sujet: str, corps: str, *,
            html: str | None = None,
            repondre_a: str = "", entetes: dict[str, str] | None = None,
            delai: float = 8) -> bool:
    """Envoie un e-mail. Rend True s'il est parti, False sinon.

    NE LÈVE JAMAIS. Les deux appelants ont déjà fait l'essentiel avant
    d'appeler (le message est en base, l'alerte est enregistrée) : un serveur
    injoignable ou un mot de passe faux ne doit coûter qu'un e-mail manqué,
    jamais la page du visiteur ni la chaîne de nuit.

    `corps` (texte) part toujours — c'est lui que lit un lecteur de flux RSS
    d'e-mails ou un client qui refuse le HTML. `html`, s'il est fourni,
    s'ajoute en ALTERNATIVE, jamais à la place : c'est au client de choisir.
    Si `html` référence `cid:{{ cid_banniere() }}`, le bandeau de marque est
    joint au message (pas chargé à distance : voir `_BANNIERE`).

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
    if html:
        msg.add_alternative(html, subtype="html")
        if f"cid:{cid_banniere()}" in html and _BANNIERE.exists():
            # La partie HTML vient d'être ajoutée : c'est la dernière du
            # message. `make_msgid` donne un Content-ID RFC-conforme (avec
            # chevrons) ; la valeur dans le HTML, elle, ne les porte pas.
            partie_html = msg.get_payload()[-1]
            partie_html.add_related(
                _BANNIERE.read_bytes(), maintype="image", subtype="png",
                cid=f"<{cid_banniere()}>")
    try:
        with smtplib.SMTP_SSL(hote, port, timeout=delai,
                              context=ssl.create_default_context()) as serveur:
            serveur.login(utilisateur, mdp)
            serveur.send_message(msg)
        return True
    except Exception:  # noqa: BLE001 — un e-mail manqué n'est pas une panne
        _log.exception("e-mail non envoyé (%s)", sujet)
        return False
