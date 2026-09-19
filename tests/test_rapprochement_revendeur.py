"""Coller une fiche du revendeur sur la bonne fiche produit — sans modèle
propre des deux côtés, contrairement à SHARP.

LA DIFFÉRENCE DE FOND. Avec SHARP, un modèle propre (« K7 ») se cherchait dans
un titre marchand bruyant. Ici, LES DEUX titres sont bruyants — le revendeur n'a
pas de fiche « modèle seul », une page par coloris. La seule chose qu'on sait
retirer proprement des deux côtés, c'est la couleur, avec le même vocabulaire
que le reste du pipeline. Ce fichier vérifie que cette symétrie tient, et
qu'elle ne réintroduit pas les pièges déjà fermés côté SHARP.
"""

from __future__ import annotations

from mcpipe.sources.rapprochement_revendeur import Candidat, _sans_couleur
from mcpipe.sources.correspondance import contient, jetons


def _c(url: str, modele: str, **valeurs) -> Candidat:
    return Candidat(url=url, marque="HJC", jetons=_sans_couleur(modele),
                    valeurs=valeurs or {"calotte": "fibre"})


# --- la couleur retirée des DEUX côtés, avec le même vocabulaire -------------

def test_la_couleur_disparait_du_titre_revendeur():
    """« HJC RPHA 12 Dravix Black-Grey-Red MC1SF » perd ses couleurs, garde
    le reste — y compris le code coloris marchand, qui n'est pas un mot de
    couleur reconnu et ne doit pas disparaître avec elles."""
    jt = _sans_couleur("HJC RPHA 12 Dravix Black-Grey-Red MC1SF")
    assert "black" not in jt and "grey" not in jt and "red" not in jt
    # `jetons()` sépare lettres et chiffres : "MC1SF" devient ['mc', '1', 'sf'].
    assert "rpha" in jt and "12" in jt and "dravix" in jt and "mc" in jt


def test_la_couleur_disparait_du_titre_marchand():
    """La même liste que `normalize`/`match` — 313 000 fiches, six langues de
    marchand — pas une deuxième liste inventée ici qui dériverait un jour de
    la première."""
    jt = _sans_couleur("Casque intégral HJC RPHA 12 Noir Mat")
    assert "noir" not in jt and "mat" not in jt
    assert "rpha" in jt and "12" in jt


def test_les_deux_titres_se_rejoignent_une_fois_la_couleur_partie():
    """Le cas nominal : deux titres bruyants, débarrassés chacun de sa
    couleur, qui se recouvrent sur le nom du modèle."""
    notre_titre = _sans_couleur("Casque intégral HJC RPHA 12 Noir Mat")
    leur_titre = _sans_couleur("HJC RPHA 12 Dravix Black-Grey-Red MC1SF")
    court, long_ = (notre_titre, leur_titre) if len(notre_titre) <= len(leur_titre) \
        else (leur_titre, notre_titre)
    assert contient(long_, court)


# --- les pièges déjà fermés côté SHARP tiennent aussi ici ---------------------

def test_un_modele_prolonge_ne_colle_pas_a_l_ancien():
    """Le même défaut que HJC C91N / C91 côté SHARP, avec les mêmes mots : le
    titre du revendeur peut nommer une variante que notre propre fiche ne nomme
    pas, et inversement. La garde de prolongement doit refuser les deux."""
    court = _sans_couleur("HJC C91")
    long_faux = _sans_couleur("HJC C91N Kaon Blanc Rouge")
    assert not contient(long_faux, court)


def test_une_declinaison_de_finition_n_empeche_pas_le_rapprochement():
    """Le revers de la garde, vérifié une fois de plus : une déclinaison de
    coloris ou d'édition dont le nom ne ressemble à aucun mot de prolongement
    doit continuer à matcher."""
    court = _sans_couleur("HJC RPHA 72 Carbon")
    long_ok = _sans_couleur("HJC RPHA 72 Carbon Fynex")
    assert contient(long_ok, court)


# --- ce qui se vend dans le rayon sans être un casque, encore --------------

def test_un_accessoire_revendeur_est_deja_ecarte_a_la_lecture():
    """Ce rapprochement s'appuie sur `source_revendeur`, qui ne contient déjà
    plus d'accessoire — `revendeur.lire()` les rejette avant l'écriture. Ce
    test documente que la garde est bien la même fonction, pas une copie qui
    pourrait diverger."""
    from mcpipe.sources.revendeur import lire
    from mcpipe.sources.correspondance import est_un_casque
    assert lire.__globals__["est_un_casque"] is est_un_casque
