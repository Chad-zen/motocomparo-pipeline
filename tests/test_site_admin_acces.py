"""`/admin` réservé au réseau local : la classification d'adresse ne doit pas
mentir.

Trouvé en revue de sécurité (2026-09-28) : `_RESEAU_LOCAL` comparait l'adresse
du visiteur à une liste de PRÉFIXES DE TEXTE, dont `"172.2"`. Une adresse
publique comme 172.200.1.1 ou 172.255.255.255 — hors du bloc privé
172.16.0.0/12 — commence aussi par "172.2" et passait donc pour "réseau
local". Sans `ADMIN_MDP` renseigné, n'importe quel visiteur dont l'adresse
tombait dans cette plage ouvrait `/admin` (messages de contact avec e-mails,
gestion des codes promo) sans mot de passe.

Ces vérifications n'ouvrent aucune connexion : `_admin_autorise` ne lit la
base que lorsque l'accès est déjà permis, elle peut donc être testée seule.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def sans_mdp(monkeypatch):
    monkeypatch.delenv("ADMIN_MDP", raising=False)


class _RequeteFactice:
    def __init__(self, hote: str | None):
        self.headers: dict[str, str] = {}
        self.client = _ClientFactice(hote) if hote is not None else None


class _ClientFactice:
    def __init__(self, hote: str):
        self.host = hote


@pytest.mark.parametrize("hote", [
    "127.0.0.1",
    "::1",
    "10.0.0.1",
    "192.168.1.5",
    "172.16.0.1",
    "172.29.9.9",
    "172.31.255.255",
    "localhost",
])
def test_reseau_local_reconnu(sans_mdp, hote):
    from mcsite.app import _admin_autorise

    assert _admin_autorise(_RequeteFactice(hote)) is None


@pytest.mark.parametrize("hote", [
    "172.2.1.1",       # préfixe texte "172.2" — hors 172.16.0.0/12
    "172.200.1.1",
    "172.255.255.255",
    "172.32.0.1",       # juste après la fin du bloc privé
    "203.0.113.5",       # une adresse publique quelconque
    "8.8.8.8",
])
def test_adresse_publique_refusee(sans_mdp, hote):
    from mcsite.app import _admin_autorise

    refus = _admin_autorise(_RequeteFactice(hote))
    assert refus is not None
    assert refus.status_code == 403
