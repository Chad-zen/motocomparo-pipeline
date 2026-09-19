"""L'analyseur des fiches du revendeur — et les deux défauts trouvés en le
faisant tourner sur de vraies pages, pas sur des suppositions.

CE QUI DIFFÈRE DE SHARP. Le revendeur n'est pas un organisme public : ce qu'on en
garde est factuel (le tableau technique, généré par leur boutique) ou lu en
PROSE avec la même prudence qu'une description marchande (poids, homologation).
Jamais leurs notes éditoriales, jamais leur texte de vente.

Les fragments HTML sont ceux de vraies fiches (AGV, HJC, Shark, Scorpion),
relevés le 19/09/2026 — jamais inventés.
"""

from __future__ import annotations

import pytest

from mcpipe.sources import revendeur


def _page(titre_complet: str, lignes_table: str, corps: str = "") -> str:
    """Assemble une page minimale, sur le squelette réel de la boutique."""
    return f"""
<html><head><title>{titre_complet}</title></head><body>
<table class="data table additional-attributes" id="product-attribute-specs-table">
<tbody>{lignes_table}</tbody>
</table>
<div class="product-description">{corps}</div>
</body></html>
"""


def _ligne(libelle: str, valeur: str) -> str:
    return (f'<tr><th class="col label" scope="row">{libelle}</th>'
            f'<td class="col data" data-th="{libelle}">{valeur}</td></tr>')


# --- le titre : trouvé dans <title>, pas dans un <h1> --------------------------

def test_le_titre_vient_de_title_pas_d_un_h1():
    """La page ne rend jamais de `<h1>` textuel sur une fiche produit — vérifié
    sur une vraie fiche avant d'écrire l'analyseur, pas supposé. `<title>`
    porte le même nom, suivi d'un slogan commercial."""
    page = _page("HJC RPHA 11 Joker  + Livraison &amp; Retour Gratuits! | 24% SALE!",
                 _ligne("Marque", "HJC"))
    f = revendeur.lire("https://x/hjc-rpha-11-joker.html", page, "casques/casques-integraux.html")
    assert f is not None
    assert f.modele == "HJC RPHA 11 Joker"


def test_le_slogan_ne_reste_pas_colle_au_nom():
    page = _page("Shark Spartan RS Blank | -30% aujourd'hui",
                 _ligne("Marque", "Shark"))
    f = revendeur.lire("https://x/shark-spartan-rs-blank.html", page, "casques/casques-integraux.html")
    assert f.modele == "Shark Spartan RS Blank"


# --- le tableau technique : vers le MÊME vocabulaire que les flux -------------

def test_la_matiere_rejoint_le_vocabulaire_des_flux():
    """« Fibre de Verre » chez le revendeur doit devenir « fibre », le mot exact
    qu'écrit `caracteristiques/casque.py` — pour qu'une page produit n'ait
    jamais à connaître deux vocabulaires pour la même idée."""
    page = _page("HJC RPHA 72 Carbon",
                 _ligne("Marque", "HJC") + _ligne("Matériel", "Fibre de Verre")
                 + _ligne("Nombre de coques", "3") + _ligne("Fermeture du casque", "Double-D"))
    f = revendeur.lire("https://x/hjc-rpha-72-carbon.html", page, "casques/casques-integraux.html")
    assert f.matiere == "fibre"
    assert f.nombre_coques == 3
    assert f.fermeture == "double-D"


def test_une_matiere_inconnue_reste_absente():
    """En cas de doute, `None` — la même règle que partout ailleurs dans ce
    projet. On ne force pas une valeur du flux sur un mot qu'on ne reconnaît
    pas."""
    page = _page("Test Helmet", _ligne("Marque", "Test") + _ligne("Matériel", "Kevlar tressé"))
    f = revendeur.lire("https://x/test-helmet.html", page, "casques/casques-integraux.html")
    assert f.matiere is None


def test_les_fonctionnalites_sont_une_liste_pas_une_phrase():
    page = _page("HJC RPHA 11 Joker",
                 _ligne("Marque", "HJC")
                 + _ligne("Caractéristiques",
                          "décrochage rapide d'urgence, Testé en soufflerie, Doublure amovible"))
    f = revendeur.lire("https://x/hjc-rpha-11-joker.html", page, "casques/casques-integraux.html")
    assert f.fonctionnalites == ["décrochage rapide d'urgence", "Testé en soufflerie",
                                 "Doublure amovible"]


# --- poids et homologation : lus en PROSE, avec la même garde que les flux ----

def test_le_poids_se_lit_dans_le_texte_de_presentation():
    page = _page(
        "Shark Ridill 2",
        _ligne("Marque", "Shark"),
        corps="En taille M, le Ridill 2 pèse environ 1459 grams, ce qui en fait "
              "un des plus légers de sa catégorie.")
    f = revendeur.lire("https://x/shark-ridill-2.html", page, "casques/casques-integraux.html")
    assert f.poids_g == 1459


def test_un_nombre_hors_fourchette_n_est_pas_un_poids():
    """900 à 2500 g : la même garde que le rayon casque. « 50 grams » est la
    tolérance annoncée sur le poids, pas le poids lui-même — et ne doit pas la
    remplacer si elle apparaît seule dans une autre phrase."""
    page = _page("Casque Test", _ligne("Marque", "Test"),
                 corps="Livré avec 50 grams de mousse de protection en plus.")
    f = revendeur.lire("https://x/casque-test.html", page, "casques/casques-integraux.html")
    assert f.poids_g is None


def test_l_homologation_se_lit_dans_le_texte():
    page = _page("HJC RPHA 12", _ligne("Marque", "HJC"),
                 corps="Ce casque sport-touring est certifié ECE22.06, la norme "
                       "européenne la plus récente.")
    f = revendeur.lire("https://x/hjc-rpha-12.html", page, "casques/casques-integraux.html")
    assert f.homologation == "22.06"


# --- le défaut trouvé en relisant : une pièce détachée dans le rayon ----------

def test_un_ecran_de_rechange_n_est_pas_un_casque():
    """Relevé dans le rayon « casques modulables » lors du premier essai :
    « Scorpion EXO-TECH Visor KDF-18 » — un écran vendu seul, sans le mot
    « casque » ni « helmet » dans son nom. `est_un_casque` a d'abord laissé
    passer parce que « visor » (anglais) n'était pas dans la liste des mots
    d'accessoire, qui n'avait que « visière » (français)."""
    page = _page("Scorpion EXO-TECH Visor KDF-18", _ligne("Marque", "Scorpion"))
    f = revendeur.lire("https://x/scorpion-exo-tech-visor-kdf-18.html", page,
                      "casques/casques-modulables.html")
    assert f is None


def test_une_mentonniere_de_rechange_n_est_pas_un_casque():
    page = _page("HJC Mentonnière RPHA 90S Blanc Perle", _ligne("Marque", "HJC"))
    f = revendeur.lire("https://x/hjc-mentonniere-rpha-90s.html", page,
                      "casques/casques-integraux.html")
    assert f is None


def test_un_vrai_casque_reste_accepte():
    page = _page("HJC RPHA 12 Dravix", _ligne("Marque", "HJC"))
    f = revendeur.lire("https://x/hjc-rpha-12-dravix.html", page, "casques/casques-integraux.html")
    assert f is not None


# --- sans marque, aucun rapprochement n'est possible --------------------------

def test_une_fiche_sans_marque_est_ecartee():
    page = _page("Un Casque Sans Marque Identifiee", "")
    f = revendeur.lire("https://x/sans-marque.html", page, "casques/casques-integraux.html")
    assert f is None


# --- la panne silencieuse ------------------------------------------------------

def test_le_releve_refuse_de_s_enregistrer_s_il_est_muet():
    """La même garde que pour SHARP. Si la boutique change son thème,
    l'analyseur rendra des fiches vides sans lever d'erreur, et on écrasera de
    bonnes lignes par du néant."""
    muettes = [revendeur.Fiche(url=f"https://x/{i}") for i in range(20)]
    with pytest.raises(RuntimeError, match="structure"):
        revendeur._exiger(muettes)


def test_le_releve_refuse_une_liste_vide():
    with pytest.raises(RuntimeError):
        revendeur._exiger([])


def test_une_fiche_partiellement_remplie_ne_bloque_pas_tout():
    bonnes = [revendeur.Fiche(url=f"https://x/{i}", marque="HJC", matiere="fibre")
              for i in range(15)]
    bonnes += [revendeur.Fiche(url="https://x/vieux", marque="HJC")]     # sans matière
    revendeur._exiger(bonnes)      # ne doit rien lever
