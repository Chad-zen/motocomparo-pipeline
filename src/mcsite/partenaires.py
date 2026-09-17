"""Les bannières des marchands partenaires.

Relevées le 17/09/2026 dans les deux plateformes d'affiliation : Effinity pour
Speedway, La Bécanerie, Maxxess et Moto-Axxe ; Kwanko pour Motoblouz. FC-Moto
est chez Webgains, qui n'a pas de bannière pour ce programme.

CE QUI EST SERVI, ET POURQUOI
=============================

Chaque plateforme fournit un code tout fait : un lien de clic **et** une image
servie par son propre serveur de suivi. Cette seconde partie est un pixel de
mesure : le serveur de la régie voit passer chaque visiteur, sur chaque page,
qu'il clique ou non. Kwanko l'écrit lui-même à côté de son code : « vous ne
bénéficiez pas de la prise en charge automatique du consentement de vos
visiteurs ; l'ensemble des actions réalisées seront donc considérées comme
non-consenties ».

Or la page « À propos » promet aujourd'hui que le site ne dépose aucun cookie et
n'utilise aucun outil de mesure d'audience, avec deux réserves énoncées : les
polices de Google et les photos servies par les marchands.

On garde donc le LIEN de suivi — il ne se déclenche qu'au clic, exactement
comme les boutons « Voir l'offre » déjà en place et déjà déclarés — et on prend
l'image **chez le marchand**, à l'adresse que la régie elle-même redirige. Une
bannière Speedway est alors, techniquement, la même chose qu'une photo de
produit Speedway : une image servie par Speedway. La troisième réserve de la
page reste vraie sans rien ajouter.

Ce que ça coûte : les régies ne comptent pas les affichages. Sur ces programmes
la rémunération se fait au clic et à la vente, pas à l'affichage — le revenu est
donc inchangé. Ce que ça peut coûter aussi : les conditions générales des régies
demandent en général d'employer leur code tel quel. C'est une décision de la
propriétaire, pas une décision technique ; `EMPREINTE_REGIE` la bascule d'un
seul réglage, sans toucher au reste.
"""

from __future__ import annotations

import os
from typing import Any

# Mettre `PUB_EMPREINTE_REGIE=1` pour servir l'image depuis le serveur de la
# régie — c'est-à-dire pour accepter le pixel de mesure, et donc devoir
# recueillir le consentement des visiteurs.
EMPREINTE_REGIE = os.environ.get("PUB_EMPREINTE_REGIE", "0") == "1"


# `clic` : l'adresse de suivi de la régie, celle qui rémunère.
# `image` : le visuel, chez le marchand.
# `regie` : le même visuel vu par le serveur de la régie, si on l'active.
PARTENAIRES: list[dict[str, str]] = [
    {
        "code": "speedway",
        "nom": "Speedway",
        "clic": "https://track.effiliation.com/servlet/effi.click?id_compteur=23313067",
        "regie": "https://track.effiliation.com/servlet/effi.show?id_compteur=23313067",
        "image": "https://medias.speedway.fr/img/effinity/300x250.gif",
        "large": "https://medias.speedway.fr/img/effinity/728x90.gif",
    },
    {
        "code": "labecanerie",
        "nom": "La Bécanerie",
        "clic": "https://track.effiliation.com/servlet/effi.click?id_compteur=23313068",
        "regie": "https://track.effiliation.com/servlet/effi.show?id_compteur=23313068",
        "image": "https://medias.la-becanerie.com/banqueImage/278/300x250-Ads-generique-01.gif",
        "large": "https://medias.la-becanerie.com/banqueImage/278/728x90-Ads-generique-01.gif",
    },
    {
        "code": "maxxess",
        "nom": "Maxxess",
        "clic": "https://track.effiliation.com/servlet/effi.click?id_compteur=23313069",
        "regie": "https://track.effiliation.com/servlet/effi.show?id_compteur=23313069",
        "image": "https://media.maxxess.fr/communication/maxxess/Effinity/2026/DUOS_GAGNANTS/300x250.gif",
        "large": "https://media.maxxess.fr/communication/maxxess/Effinity/2026/DUOS_GAGNANTS/728x90.gif",
    },
    {
        "code": "motoaxxe",
        "nom": "Moto-Axxe",
        "clic": "https://track.effiliation.com/servlet/effi.click?id_compteur=23313070",
        "regie": "https://track.effiliation.com/servlet/effi.show?id_compteur=23313070",
        "image": "https://media.moto-axxe.fr/communication/motoaxxe/Effinity/2026/LE-MOIS-DU-CASQUES/300x250.gif",
        "large": "https://media.moto-axxe.fr/communication/motoaxxe/Effinity/2026/LE-MOIS-DU-CASQUES/728x90.gif",
    },
    {
        "code": "motoblouz",
        "nom": "Motoblouz",
        # Chez Kwanko, chaque FORMAT a son propre code — contrairement à
        # Effinity, où un seul identifiant sert tout un programme. Le 300x250
        # finit en E6F1B3, le 728x90 en E6F1B6 : une lettre d'écart, et les
        # revenus d'un format iraient au compteur de l'autre.
        "clic": "https://pkw.motoblouz.com/?P41221589E6F1B3",
        "regie": "https://pkw.motoblouz.com/?a=P41221589E6F1B3",
        # Motoblouz sert son visuel depuis son propre domaine de tracking : ici
        # les deux adresses coïncident, il n'y a pas de tiers supplémentaire.
        "image": "https://pkw.motoblouz.com/?a=P41221589E6F1B3",
        "clic_large": "https://pkw.motoblouz.com/?P41221589E6F1B6",
        "large": "https://pkw.motoblouz.com/?a=P41221589E6F1B6",
    },
]


def bandeaux(format: str = "carre") -> list[dict[str, Any]]:
    """Les bannières telles que la page doit les rendre.

    `format` vaut « carre » (300x250, en bas des pages de résultats) ou
    « large » (728x90, en travers de l'accueil). Le second est le seul qui
    tienne dans la respiration entre deux étagères : un pavé de 250 px de haut
    y couperait le fil de lecture, une bande de 90 px le ponctue.

    La rotation se fait côté navigateur, pas ici : les pages sont mises en
    cache une heure par nginx, et un tirage au sort côté serveur figerait une
    bannière par page pour toute cette heure — un marchand aurait la page
    d'accueil, un autre les casques, et ça ne bougerait plus.
    """
    large = format == "large"
    return [
        {
            "code": p["code"],
            "nom": p["nom"],
            # Kwanko donne un lien PAR FORMAT ; Effinity un seul par programme.
            # `clic_large` n'existe donc que là où il diffère.
            "clic": p.get("clic_large", p["clic"]) if large else p["clic"],
            "image": (p["regie"] if EMPREINTE_REGIE
                      else (p["large"] if large else p["image"])),
            "large": large,
        }
        for p in PARTENAIRES
    ]
