"""Une fiche de pieces qui melange deux numeros de reference est separee (23/10/2026)."""

from mcpipe.separer_references import planifier, references_du_titre


def test_les_references_du_titre_ignorent_le_code_barres():
    assert references_du_titre("Kit Vis Lightech Ergal Or 1114850003", "8052393379982") == {"1114850003"}
    assert references_du_titre("EAN 8052393379982", "8052393379982") == set()
    assert references_du_titre("Pignon 520 pas") == set()


def test_le_kit_lightech_est_separe_en_deux_fiches():
    offres = [
        (1, "8052393379982", 10, "Kit Vis De Moteur Lightech Ergal Or 1114850003 - Carenage", "linked"),
        (2, "8052393430362", 10, "Kit Vis De Moteur Lightech Ergal Or 1114815003 - Carenage", "linked"),
    ]
    assert planifier(offres) == {"8052393379982": "1114850003", "8052393430362": "1114815003"}


def test_un_seul_numero_ne_se_separe_pas():
    offres = [(1, "111", 10, "Kit 1114850003 taille S", "linked"), (2, "222", 10, "Kit 1114850003 taille M", "linked")]
    assert planifier(offres) is None


def test_deux_marchands_qui_nomment_differemment_le_meme_code_barres_ne_decident_pas():
    # le code-barres 111 a deux numeros selon le marchand : ambigu, pas de preuve d'un meme marchand
    offres = [(1, "111", 10, "Kit 1114850003", "linked"), (2, "111", 20, "Kit 1114815003", "linked")]
    assert planifier(offres) is None


def test_un_code_barres_ambigu_reste_sur_la_fiche_d_origine():
    offres = [
        (1, "111", 10, "Kit 1114850003", "linked"), (2, "222", 10, "Kit 1114815003", "linked"),
        (3, "333", 20, "Kit 1114850003 et 1114815003", "linked"),
    ]
    plan = planifier(offres)
    assert plan == {"111": "1114850003", "222": "1114815003"}
