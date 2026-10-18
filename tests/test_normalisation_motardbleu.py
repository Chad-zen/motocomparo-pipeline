"""Les valeurs du flux Awin de Motard Bleu (18/10/2026) que le code lisait de travers."""

import pytest

from mcpipe import textnorm as tn


@pytest.mark.parametrize("brut, attendu", [
    ("S (55/56 cm)", "S5556"),     # = ce que FC-Moto donne pour « S (55/56) »
    ("XL (61/62 cm)", "XL6162"),
    ("S (55/56)", "S5556"),        # FC-Moto, inchange
    ("Taille 8", "8"),
    ("Taille 13", "13"),
    ("8", "8"),                    # inchange
    ("TU", "TU"),
    ("2XL", "2XL"),
    ("XXL", "2XL"),
    ("L (152cm)", "L152CM"),       # taille d'enfant de La Becanerie : pas un tour de tete
])
def test_libelles_de_taille(brut, attendu):
    assert tn.size_code(brut, None, None, None)[0] == attendu


def test_deux_libelles_d_une_meme_taille_se_rejoignent():
    mb = tn.size_code("M (57/58 cm)", None, None, None)[0]
    fc = tn.size_code("M (57/58)", None, None, None)[0]
    assert mb == fc


@pytest.mark.parametrize("brut", ["Argenté", "argenté"])
def test_argente_est_lu(brut):
    canon, premiere, _ = tn.colour(brut)
    assert "SI" in canon


def test_argente_n_ajoute_pas_de_couleur_a_une_couleur_connue():
    # le repli ne joue que sans couleur connue : « noir/argenté » reste « noir »
    # tant que le mot « argente » n'est que dans le repli, comme « argentee ».
    assert tn.colour("Noir Argenté")[0] == "BK"
    assert tn.colour("Argenté")[0] == "SI"


@pytest.mark.parametrize("genre, age, attendu", [
    ("Unisex", "Adulte", "U-A"),
    ("Male", "Adulte", "H-A"),
    ("Female", "Adulte", "F-A"),
    ("Unisex", "Junior", "U-E"),
    ("Male", "Baby", "H-E"),
    ("Unisex", "N/A", "U-A"),
    ("Male", "", "H-A"),
])
def test_genre_et_age_du_flux(genre, age, attendu):
    assert tn.genre_age("blouson moto", genre, age) == attendu


def test_stella_est_une_femme_meme_declaree_male():
    assert tn.genre_age(tn.norm_txt("Blouson Alpinestars Stella Missile"), "Male", "Adulte") == "F-A"


def test_un_ean_dont_la_cle_est_fausse_est_ecarte():
    assert tn.valid_gtin("3661615751564") == "3661615751564"
    assert tn.valid_gtin("3700611016437") is None   # l'un des 2 707 EAN invalides du flux
    assert tn.valid_gtin("43350729") is None        # 8 chiffres, cle fausse


# --- le coloris complet, lu dans le nom du fichier image ---------------------

from mcpipe.feeds import FEEDS  # noqa: E402
from mcpipe.normalize import _couleur  # noqa: E402

_MB = FEEDS["motardbleu"]


def _ligne(colour, image):
    return {"colour": colour, "merchant_image_url": image}


@pytest.mark.parametrize("colour, image, attendu_canon", [
    # le champ dit « Noir », l'image precise noir + rouge : on prend l'image
    ("Noir", "https://x/4/s/4square_gantpulsarnoirrouge_noir-rouge_1.jpg", "BK-RD"),
    ("Noir", "https://x/4/s/4square_gantpulsarnoirjaune_noir-jaune_1.jpg", "BK-YE"),
    ("Noir", "https://x/4/s/4square_gantpulsarnoirgris_noir-gris_1.jpg", "BK-GY"),
    # le champ suffit, l'image ne precise rien
    ("Noir", "https://x/4/s/4square_gantpulsarhnoir_noir_1.jpg", "BK"),
    # le champ dit « Vert », l'image dit « khaki » (meme code) : on garde le champ
    ("Vert", "https://x/i/ixon_100101188-8001_khaki_1.jpg", "GN"),
    # le champ n'est pas lisible (turquoise n'a pas de code), l'image l'est
    ("Turquoise", "https://x/a/b_modele_noir-bleu_2.jpg", "BK-BL"),
])
def test_le_coloris_complet_precise_le_champ(colour, image, attendu_canon):
    assert tn.colour(_couleur(_MB, _ligne(colour, image)))[0] == attendu_canon


def test_l_image_ne_contredit_jamais_le_champ():
    # champ rouge, image noir-blanc : le champ reste la parole du marchand
    assert _couleur(_MB, _ligne("Rouge", "https://x/a_modele_noir-blanc_1.jpg")) == "Rouge"


def test_une_image_sans_coloris_laisse_le_champ():
    assert _couleur(_MB, _ligne("Noir", "https://x/a/b/photo.jpg")) == "Noir"
    assert _couleur(_MB, _ligne("Noir", "")) == "Noir"


def test_les_autres_plateformes_ne_sont_pas_touchees():
    effinity = FEEDS["speedway"]
    row = {"color": "Noir", "image_link": "https://x/a_modele_noir-rouge_1.jpg"}
    assert _couleur(effinity, row) == "Noir"


@pytest.mark.parametrize("brut, attendu", [
    ("GPR Exhaust", "gpr"), ("GPR", "gpr"),
    ("Nexx Helmets", "nexx"), ("NEXX", "nexx"),
    ("Shot Race Gear", "shot"), ("Pull-in moto", "pullin"),
    ("MIW", "meiwa"), ("KYB", "kayaba"),
])
def test_les_noms_de_marque_de_motard_bleu_se_lisent_comme_ceux_des_autres(brut, attendu):
    assert tn.brand(brut)[0] == attendu


def test_les_alias_de_motard_bleu_ne_changent_aucun_code_existant():
    # un alias dont la cle serait deja un code chez un autre marchand changerait des adresses de fiche
    for cle in ("blackbirdracing", "samcosport", "seven", "ngbrakedisc", "vectorsecurity", "optimate"):
        assert tn.brand(cle)[0] == cle
