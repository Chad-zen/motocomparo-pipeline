"""Les calculs lancés depuis l'administration (16/10/2026)."""

from __future__ import annotations

from mcpipe import taches


def test_une_demande_ne_designe_qu_une_tache_de_la_liste():
    assert taches.demander("rm -rf /") is None
    assert taches.demander("") is None
    assert taches.demander("../../etc/passwd") is None


def test_chaque_tache_n_appelle_que_des_commandes_mcpipe_connues():
    import mcpipe.cli as cli

    connues = {c.name or c.callback.__name__.replace("_", "-") for c in cli.app.registered_commands}
    for cle, t in taches.TACHES.items():
        assert t.etapes, cle
        for etape in t.etapes:
            assert etape[0] in connues, (cle, etape)


def test_aucune_tache_ne_lance_le_rapprochement_complet_ni_la_chaine_de_nuit():
    """`match` (arrêt du site) et la chaîne entière ne se lancent pas d'un clic."""
    for t in taches.TACHES.values():
        for etape in t.etapes:
            assert etape[0] not in ("match", "fetch", "load", "reset")
            assert "--reset" not in etape


def test_l_unite_systemd_redemarre_le_site_en_root_par_drapeau():
    s = open("ops/deploiement/systemd/mcpipe-taches.service", encoding="utf-8").read()
    assert "ExecStartPost=+" in s and ".redemarrer-site" in s
    assert "User=motocomparo" in s
