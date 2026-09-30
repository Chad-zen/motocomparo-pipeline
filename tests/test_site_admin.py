"""Qui peut ouvrir `/admin` : réseau local testé par plage, jamais par préfixe."""

import pytest

from mcsite.app import _reseau_local


@pytest.mark.parametrize("hote", ["127.0.0.1", "::1", "localhost", "10.0.0.2",
                                  "192.168.1.5", "172.16.0.1", "172.20.0.1",
                                  "172.31.255.254"])
def test_reseau_local_accepte(hote):
    assert _reseau_local(hote)


# 172.2.x.x et 172.200-255.x.x commencent par « 172.2 » mais sont publiques :
# l'ancien test par préfixe les laissait entrer.
@pytest.mark.parametrize("hote", ["172.2.0.1", "172.217.1.1", "172.232.4.4",
                                  "172.32.0.1", "8.8.8.8", "169.254.1.1", "",
                                  "testclient", "127.0.0.1.evil"])
def test_reseau_public_refuse(hote):
    assert not _reseau_local(hote)
