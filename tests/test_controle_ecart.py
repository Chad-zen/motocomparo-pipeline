from mcpipe.controle_ecart import mots_qui_different, niveau


def test_le_mot_qui_differencie_un_pinlock_de_sa_visiere():
    # fiche Airoh ST, 22/10/2026 : 34,90 EUR contre 54,95 EUR, ecart de 57 %
    mots = mots_qui_different("Airoh ST Pinlock Visière", "Airoh ST 701/ST 501/Valor, visière , couleur: 85% Teinté")
    assert "pinlock" in mots.split()


def test_les_niveaux_du_controle():
    assert niveau(1.57, 2, True) == "fort"     # un meme marchand, deux codes-barres
    assert niveau(2.4, 1, False) == "fort"     # plus du double
    assert niveau(1.6, 2, False) == "moyen"    # plusieurs codes-barres
    assert niveau(1.6, 1, False) == "faible"   # un seul code-barres : promo ou erreur de prix
