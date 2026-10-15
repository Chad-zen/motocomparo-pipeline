"""Les alertes de baisse de prix — les règles, et le passage de nuit.

Un visiteur laisse son adresse sur une fiche ; il confirme par e-mail (double
opt-in) ; chaque nuit, après `freshness`, `mcpipe alertes` regarde si la fiche
a désormais une offre fraîche, en stock, au prix qu'il attend, et le prévient
UNE fois. Le site (formulaire, confirmation, désinscription) et la commande de
nuit lisent les mêmes règles ici, pour qu'ils ne puissent pas diverger sur ce
qu'est « une baisse ».

Ce qui compte comme une offre achetable est exactement ce qui fixe le
« meilleur prix » de la fiche (voir `freshness._RECOMPUTE_MIN_PRICE`) : liée,
fraîche au sens de `_FRESH`, prix connu, pas déclarée en rupture, chez un
marchand affiché. Prévenir d'un prix que la fiche n'afficherait pas serait
envoyer quelqu'un vers un prix qui n'existe plus — la pire faute d'un
comparateur.

Données personnelles : voir sql/028_alerte_prix.sql. Tout ce qui n'a plus
d'usage est EFFACÉ, pas désactivé (`purger`).
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row

from mcsite import labels

from . import courriel
from .db import connect
from .freshness import _FRESH

_log = logging.getLogger("mcpipe.alertes")

# Les trois durées promises au visiteur, dans le formulaire, les e-mails et
# /infos. Écrites une fois ici ; les textes les lisent.
DUREE_VIE = "6 months"          # une alerte confirmée, puis effacée
DUREE_VIE_TEXTE = "6 mois"
ATTENTE_CONFIRMATION = "7 days"  # une demande non confirmée, puis effacée
ATTENTE_TEXTE = "7 jours"

# Plafonds anti-abus. Un formulaire qui envoie un e-mail à l'adresse saisie
# peut servir à inonder la boîte d'un tiers : au plus 5 demandes de
# confirmation par adresse et par 24 h, au plus 20 alertes par adresse.
MAX_PAR_ADRESSE = 20
MAX_DEMANDES_JOUR = 5
# Redemander la même alerte encore en attente renvoie l'e-mail — le visiteur
# qui ne trouve pas le premier peut le redemander — mais trois fois au plus
# par demande : sans borne, un robot ferait partir un e-mail par requête vers
# la même adresse.
MAX_ENVOIS_CONFIRMATION = 3

# Au-delà de trois échecs SMTP d'affilée, le serveur d'envoi est en panne :
# inutile d'attendre 8 s par alerte restante. Les autres partiront la nuit
# suivante — rien n'est marqué envoyé tant qu'il n'est pas parti.
_ECHECS_MAX = 3

# Même valeur que `mcsite.queries._PRIX_SENTINELLE` : un « prix » de 9 999 €
# est un marchand qui n'en donne pas.
_PRIX_SENTINELLE = "9999.00"


def site_url() -> str:
    """La racine des liens envoyés par e-mail. Jamais lue dans la requête : un
    en-tête Host forgé ferait partir des liens vers un autre site."""
    return os.environ.get("SITE_URL", "https://motocomparo.com").strip().rstrip("/")


def nouveau_jeton() -> str:
    # 32 octets d'aléa : impossible à deviner, donc suffisant pour prouver
    # qu'on a reçu l'e-mail. Pas de compte, pas de mot de passe.
    return secrets.token_urlsafe(32)


# --- la règle -------------------------------------------------------------------

def taille_correspond(taille_alerte: str | None, size_code: str | None) -> bool:
    """Une offre vaut-elle pour la taille demandée ?

    La taille de l'alerte est le LIBELLÉ du bouton de la fiche, éventuellement
    fusionné par code-barres (« XS / 6 », voir `labels.equivalences_tailles`).
    L'offre est lue comme la fiche la lit, par `labels.size_display`.

    Une offre SANS taille lisible ne vaut pas pour une taille précise : la
    fiche la montre sous chaque filtre parce qu'elle ne sait pas, mais écrire
    « votre M est à 89 € » sur une offre qui est peut-être un XL serait faux.
    """
    if not taille_alerte:
        return True
    etiquette = labels.size_display(size_code)
    if not etiquette:
        return False
    return etiquette in {t.strip() for t in taille_alerte.split(" / ")}


def meilleure(offres: list[dict[str, Any]], taille: str | None) -> dict[str, Any] | None:
    """L'offre achetable la moins chère dans la taille demandée."""
    dans_la_taille = [o for o in offres if taille_correspond(taille, o.get("size_code"))]
    return min(dans_la_taille, key=lambda o: o["price"], default=None)


def a_prevenir(alerte: dict[str, Any], offres: list[dict[str, Any]]) -> dict[str, Any] | None:
    """L'offre dont il faut prévenir, ou None.

    - un prix visé : toute offre à ce prix ou en dessous ;
    - sinon : toute offre STRICTEMENT sous le meilleur prix du jour de la
      demande (`prix_reference`). Sans référence — la taille n'était pas
      disponible ce jour-là — la première offre achetable suffit ;
    - déjà prévenu : seulement si le prix descend ENCORE sous le dernier prix
      annoncé. Un prix qui remonte puis revient au même niveau ne réécrit pas.
    """
    o = meilleure(offres, alerte.get("taille"))
    if o is None:
        return None
    prix = Decimal(str(o["price"]))
    cible, ref, dernier = (alerte.get("prix_cible"), alerte.get("prix_reference"),
                           alerte.get("dernier_prix_notifie"))
    if cible is not None:
        if prix > Decimal(str(cible)):
            return None
    elif ref is not None and prix >= Decimal(str(ref)):
        return None
    if dernier is not None and prix >= Decimal(str(dernier)):
        return None
    return o


# --- la base --------------------------------------------------------------------

_OFFRES_ACHETABLES = f"""
SELECT DISTINCT ON (o.id)
       p.slug, o.price, m.code AS merchant,
       coalesce(v.size_code, o.raw_size) AS size_code
FROM product p
JOIN raw_offer o ON o.product_id = p.id
JOIN merchant m ON m.id = o.merchant_id AND m.affiche
LEFT JOIN offer_variant_link l ON l.raw_offer_id = o.id
LEFT JOIN variant v ON v.id = l.variant_id
WHERE p.slug = ANY(%s)
  AND o.linked_status = 'linked' AND o.price IS NOT NULL
  AND o.price <> {_PRIX_SENTINELLE} AND o.in_stock IS NOT FALSE
  AND {_FRESH}
ORDER BY o.id, v.size_code
"""


def offres_achetables(conn, slugs: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Les offres achetables aujourd'hui, par fiche. `DISTINCT ON (o.id) …
    ORDER BY o.id, v.size_code` : la même taille que celle que la fiche
    affiche pour une offre rattachée à plusieurs variantes."""
    par_fiche: dict[str, list[dict[str, Any]]] = {s: [] for s in slugs}
    if not slugs:
        return par_fiche
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_OFFRES_ACHETABLES, (list(slugs),))
        for r in cur.fetchall():
            par_fiche[r["slug"]].append(r)
    return par_fiche


def purger(conn) -> int:
    """Efface ce que le visiteur a été promis de voir effacer : les demandes
    jamais confirmées après 7 jours, les alertes confirmées après 6 mois."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM alerte_prix WHERE confirme_le IS NULL "
            f"AND cree_le < now() - interval '{ATTENTE_CONFIRMATION}'")
        n = cur.rowcount
        cur.execute(
            "DELETE FROM alerte_prix WHERE confirme_le IS NOT NULL "
            f"AND confirme_le < now() - interval '{DUREE_VIE}'")
        return n + cur.rowcount


def enregistrer_demande(conn, *, email: str, slug: str, taille: str | None,
                        prix_cible: Decimal | None,
                        prix_reference: Decimal | None) -> str | None:
    """Écrit (ou rafraîchit) une demande EN ATTENTE. Rend le jeton à envoyer
    par e-mail, ou None quand il ne faut rien envoyer.

    Le visiteur voit la MÊME réponse dans tous les cas (« si l'adresse est
    valide, un e-mail vient de partir ») : dire « vous suivez déjà cet
    article » ou « plafond atteint » apprendrait à n'importe qui qu'une adresse
    est inscrite ici.

    Les cas où rien ne part :
    - l'alerte existe déjà et est CONFIRMÉE : la modifier sans preuve de
      possession de l'adresse laisserait un tiers changer le seuil d'autrui ;
    - la demande en attente a déjà reçu ses trois e-mails ;
    - l'adresse a atteint 20 alertes, ou 5 demandes dans les 24 h.

    Connexion en autocommit attendue (celle du site).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT id, jeton, confirme_le, envois FROM alerte_prix
            WHERE email = %s AND produit_slug = %s
              AND coalesce(taille, '') = coalesce(%s, '')
        """, (email, slug, taille))
        existante = cur.fetchone()
        if existante is not None:
            if existante["confirme_le"] is not None:
                return None
            if existante["envois"] >= MAX_ENVOIS_CONFIRMATION:
                return None
            # Le seuil suit la dernière demande ; la date de création ne bouge
            # pas, l'effacement à 7 jours court depuis la première.
            cur.execute("""
                UPDATE alerte_prix SET envois = envois + 1, prix_cible = %s,
                       prix_reference = %s
                WHERE id = %s AND confirme_le IS NULL
                RETURNING jeton
            """, (prix_cible, prix_reference, existante["id"]))
            r = cur.fetchone()
            return r["jeton"] if r else None

        cur.execute("""
            SELECT count(*) AS toutes,
                   count(*) FILTER (WHERE confirme_le IS NULL
                                    AND cree_le > now() - interval '24 hours') AS du_jour
            FROM alerte_prix WHERE email = %s
        """, (email,))
        c = cur.fetchone()
        if c["toutes"] >= MAX_PAR_ADRESSE or c["du_jour"] >= MAX_DEMANDES_JOUR:
            return None
        jeton = nouveau_jeton()
        # ON CONFLICT : deux envois simultanés du même formulaire ne doivent
        # pas lever d'erreur sur l'index unique — le second ne fait rien.
        cur.execute("""
            INSERT INTO alerte_prix (email, produit_slug, taille, prix_cible,
                                     prix_reference, jeton)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING jeton
        """, (email, slug, taille, prix_cible, prix_reference, jeton))
        r = cur.fetchone()
        return r["jeton"] if r else None


# --- les e-mails ----------------------------------------------------------------

_SIGNATURE = ("--\nMotoComparo, comparateur de prix d'équipement moto\n"
              "Vos données : {site}/infos#donnees")


def courriel_confirmation(*, titre: str, taille: str | None, prix_cible: Any,
                          prix_actuel: Any, jeton: str) -> tuple[str, str]:
    site = site_url()
    seuil = (f"dès qu'une offre passe à {labels.price(prix_cible)} ou moins"
             if prix_cible is not None else
             f"dès qu'une offre passe sous {labels.price(prix_actuel)}, "
             "le meilleur prix d'aujourd'hui" if prix_actuel is not None else
             "dès qu'une offre est disponible")
    corps = (
        "Bonjour,\n\n"
        "Quelqu'un — vous, sans doute — a demandé sur MotoComparo à être prévenu "
        "à cette adresse quand le prix de cet article baisse :\n\n"
        f"  {titre}{' — taille ' + taille if taille else ''}\n"
        f"  Prévenu {seuil}.\n\n"
        f"Pour activer l'alerte, ouvrez ce lien dans les {ATTENTE_TEXTE} :\n"
        f"{site}/alertes/confirmer?jeton={jeton}\n\n"
        "Sans confirmation, nous ne vous écrirons plus et cette demande sera "
        f"effacée sous {ATTENTE_TEXTE}. Une fois confirmée, l'alerte dure "
        f"{DUREE_VIE_TEXTE}, puis s'efface d'elle-même ; chaque e-mail contient "
        "un lien pour l'arrêter.\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez simplement ce "
        "message.\n\n" + _SIGNATURE.format(site=site))
    return f"Confirmez votre alerte de prix : {titre}", corps


def liens_sortie(jeton: str) -> dict[str, str]:
    site = site_url()
    return {"arreter": f"{site}/alertes/arreter?jeton={jeton}",
            "tout": f"{site}/alertes/tout-supprimer?jeton={jeton}"}


def courriel_baisse(*, titre: str, slug: str, taille: str | None, prix: Any,
                    marchand: str, jeton: str, expire_le: Any) -> tuple[str, str, dict]:
    site = site_url()
    liens = liens_sortie(jeton)
    expire = expire_le.strftime("%d/%m/%Y") if expire_le else ""
    corps = (
        "Bonjour,\n\n"
        f"Le prix que vous attendiez est là :\n\n"
        f"  {titre}{' — taille ' + taille if taille else ''}\n"
        f"  {labels.price(prix)} chez {labels.merchant(marchand)}\n\n"
        f"Comparer les offres : {site}/p/{slug}\n\n"
        "Prix relevé cette nuit chez le marchand ; celui qui fait foi est celui "
        "affiché sur son site au moment de la commande.\n\n"
        "Nous vous écrirons de nouveau seulement si le prix baisse encore"
        + (f", et au plus tard jusqu'au {expire}, date où l'alerte s'efface."
           if expire else ".") + "\n\n"
        f"Arrêter cette alerte : {liens['arreter']}\n"
        f"Effacer toutes vos alertes et votre adresse : {liens['tout']}\n\n"
        + _SIGNATURE.format(site=site))
    # Désinscription en un clic depuis le logiciel de messagerie (RFC 8058) :
    # Gmail et les autres l'affichent à côté de l'expéditeur.
    entetes = {"List-Unsubscribe": f"<{liens['arreter']}>",
               "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
               "Auto-Submitted": "auto-generated"}
    return f"Baisse de prix : {titre} à {labels.price(prix)}", corps, entetes


def titre_fiche(best_title: str | None, model_display: str, brand_code: str) -> str:
    """Le nom affiché sur la fiche, sans la taille ni la queue de rayon — mêmes
    retraits que `mcsite.app._nom`, sans importer l'application web."""
    t = (best_title or "").strip()
    if not t:
        return model_display
    return labels.sans_taille_finale(labels.sans_queue_de_rayon(t, brand_code or ""))


# --- le passage de nuit --------------------------------------------------------

@dataclass
class AlertesResultat:
    effacees: int
    examinees: int
    envoyees: int
    echecs: int
    smtp: bool
    seconds: float


def run_alertes() -> AlertesResultat:
    """Prévient les alertes confirmées dont le prix est atteint. Rejouable :
    une alerte n'est marquée qu'après le départ de son e-mail, et ne repart
    que sur une baisse supplémentaire.

    Ne lève pas pour une panne d'envoi : la chaîne de nuit ne doit pas
    s'arrêter parce que la boîte mail est injoignable. Une panne de BASE,
    elle, remonte — c'est une vraie panne.
    """
    t0 = time.time()
    conn = connect()
    try:
        effacees = purger(conn)
        conn.commit()
        if not courriel.configure():
            # Aucune alerte n'a pu être confirmée sans e-mail ; rien à faire.
            _log.warning("alertes : SMTP non configuré, aucun envoi")
            return AlertesResultat(effacees, 0, 0, 0, False, time.time() - t0)

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"""
                SELECT a.id, a.email, a.produit_slug, a.taille, a.prix_cible,
                       a.prix_reference, a.dernier_prix_notifie, a.jeton,
                       a.confirme_le + interval '{DUREE_VIE}' AS expire_le,
                       p.model_display, p.brand_code, s.best_title
                FROM alerte_prix a
                JOIN product p ON p.slug = a.produit_slug
                LEFT JOIN product_stats s ON s.product_id = p.id
                WHERE a.confirme_le IS NOT NULL
                ORDER BY a.id
            """)
            alertes = cur.fetchall()
        offres = offres_achetables(conn, sorted({a["produit_slug"] for a in alertes}))

        envoyees = echecs = d_affilee = 0
        for a in alertes:
            o = a_prevenir(a, offres.get(a["produit_slug"], []))
            if o is None:
                continue
            if d_affilee >= _ECHECS_MAX:
                echecs += 1
                continue
            sujet, corps, entetes = courriel_baisse(
                titre=titre_fiche(a["best_title"], a["model_display"], a["brand_code"]),
                slug=a["produit_slug"], taille=a["taille"], prix=o["price"],
                marchand=o["merchant"], jeton=a["jeton"], expire_le=a["expire_le"])
            if courriel.envoyer(a["email"], sujet, corps, entetes=entetes, delai=20):
                # Commit alerte par alerte : si la chaîne meurt au milieu, ce qui
                # est parti est marqué et ne repartira pas demain.
                conn.execute(
                    "UPDATE alerte_prix SET dernier_prix_notifie = %s, notifie_le = now() "
                    "WHERE id = %s", (o["price"], a["id"]))
                conn.commit()
                envoyees += 1
                d_affilee = 0
            else:
                echecs += 1
                d_affilee += 1
        return AlertesResultat(effacees, len(alertes), envoyees, echecs, True,
                               time.time() - t0)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
