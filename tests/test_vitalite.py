"""Un flux mort ne lève aucune erreur — c'est tout le problème.

Le 18/09/2026, un marchand a servi huit jours durant un fichier identique à
l'octet près. Le téléchargement disait « ok », le chargement disait « ok », et
le site affichait des prix périmés avec le même aplomb que les autres. Le
défaut a été trouvé parce que la propriétaire a cliqué sur un lien mort.

Ces vérifications tiennent la règle de détection, qui est contre-intuitive :
on ne surveille PAS les prix.
"""

from __future__ import annotations

from mcpipe.vitalite import Vitalite


def _v(retirees=0, arrivees=0, prix=0, affiche=True):
    return Vitalite(code="x", offres=100000, retirees=retirees, arrivees=arrivees,
                    prix_changes=prix, dernier_mouvement=None, affiche=affiche)


def test_les_trois_a_zero_accusent():
    assert _v(0, 0, 0).fige


def test_un_seul_mouvement_suffit_a_disculper():
    """Chacun des trois signaux pris seul ne prouve rien — c'est leur
    CONJONCTION qui accuse. Un marchand peut ne changer aucun prix pendant une
    semaine calme sans que rien n'aille mal."""
    assert not _v(retirees=1).fige
    assert not _v(arrivees=1).fige
    assert not _v(prix=1).fige


def test_le_prix_seul_ne_suffirait_pas_comme_signal():
    """Si on ne surveillait que les prix, un marchand qui n'en change aucun
    pendant une semaine calme serait accusé à tort. C'est pourquoi la règle
    exige aussi l'absence d'arrivées ET de retraits : un catalogue de dizaines
    de milliers d'articles a toujours une rupture ou un réassort.

    Mesuré le 18/09 : les deux plus petits marchands du site bougeaient encore
    de 80 et 85 références, quand le mort affichait zéro sur 222 927."""
    catalogue_calme_mais_vivant = _v(retirees=80, arrivees=85, prix=0)
    assert not catalogue_calme_mais_vivant.fige
