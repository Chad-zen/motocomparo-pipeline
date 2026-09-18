"""Les quatre pièges du rayon casque, trouvés en relisant l'échantillon.

AUCUN n'était visible dans les chiffres de couverture. Tous les quatre
FAISAIENT MONTER la couverture — ils ressemblaient à une bonne nouvelle. C'est
la leçon de ce fichier : un extracteur se juge en lisant ses sorties, pas en
regardant son taux de remplissage.
"""

from __future__ import annotations

from mcpipe.caracteristiques.casque import lire


def test_predispose_n_est_pas_fourni():
    """LE piège du rayon. « Prédisposé » est le mot le plus employé, et la
    première version de la garde ne le connaissait pas : elle annonçait
    « intercom fourni » sur cinq casques sur cinq alors que les cinq disaient
    « prédisposé à recevoir »."""
    for phrase in (
        "Prédisposé à recevoir le système de communication SMART HJC Bluetooth",
        "Prédisposé pour module Bluetooth/intercom",
        "Prédisposé pour recevoir le nouveau Bluetooth LS2",
        "Prédisposé à recevoir une système de communication SENA ou Cardo",
    ):
        assert lire("", phrase).intercom == "prepare", phrase


def test_pret_pour_n_est_pas_pret_a():
    """« Prêt POUR Pinlock » veut dire que la lentille n'est pas dans la boîte.
    La garde ne prévoyait que « prêt À »."""
    assert lire("", "Pare-soleil intégré Prêt pour Pinlock 70 MaxVision").pinlock == "prepare"
    assert lire("", "Préparé Pinlock mais la lentille n'est pas fournie").pinlock == "prepare"


def test_equipe_de_veut_bien_dire_fourni():
    """L'inverse doit rester vrai, sinon la garde ne sert qu'à tout refuser."""
    assert lire("", "Le casque est équipé du PINLOCK MAX VISION 70").pinlock == "fourni"
    assert lire("", "Livré avec lentille Pinlock 30").pinlock == "fourni"


def test_thermoplastique_n_est_pas_polycarbonate():
    """Le polycarbonate est un thermoplastique parmi d'autres. Les confondre
    prêtait au casque une matière qu'il n'a pas : l'ADT de KYT et de Suomy est
    un mélange maison, pas du polycarbonate."""
    assert lire("", "Coque en ADT (Advanced Thermoplastic)").calotte == "thermoplastique"
    assert lire("", "Coque en résine thermoplastique").calotte == "thermoplastique"
    assert lire("", "Coque en polycarbonate résistante").calotte == "polycarbonate"
    assert lire("", "Coque PC/ABS solide et durable").calotte == "polycarbonate"


def test_la_visiere_n_est_pas_la_calotte():
    """Un casque porte DEUX pièces en plastique et les marchands parlent des
    deux dans le même paragraphe. « Visière en polycarbonate » est vrai de
    presque tous les casques, y compris ceux dont la coque est en carbone.

    Cas réel : un KYT R2R à coque ADT annoncé « polycarbonate » sur la foi de
    sa visière."""
    t = ("Coque ADT-Advance Thermoplastique composée d'un mélange de résines. "
         "Visière en polycarbonate, résistante aux rayures")
    assert lire("", t).calotte == "thermoplastique"


def test_abs_ne_doit_pas_matcher_absorption():
    """Sans limites de mot, ABS matche « ABSorption » — qui figure dans presque
    toutes les descriptions de casque. Tout le rayon serait devenu
    « polycarbonate », et la couverture aurait bondi : le symptôme d'un faux
    positif massif ressemble exactement à une bonne nouvelle."""
    assert lire("", "Calotte offrant une excellente absorption des chocs").calotte is None


def test_le_doute_rend_rien():
    """La règle qui gouverne tout le fichier : annoncer qu'un casque est
    homologué quand il ne l'est pas n'est pas une imprécision de comparateur."""
    vide = lire("", "")
    assert vide.homologation is None and vide.calotte is None
    assert vide.renseignees() == 0
