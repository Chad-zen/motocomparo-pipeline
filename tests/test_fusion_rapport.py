"""Le rapport note les regroupements sans rien fusionner (19/10/2026).
Cas de reference : Furygan Brooks (vrai doublon, tailles complementaires) et
Falco Starboy 4 (deux chaussures differentes : memes tailles, EAN differents)."""

from mcpipe.fusion_rapport import FicheSignaux, evaluer


def _fiche(id, tailles, couleur="BK", genre="H-A", annee=None, prix=(150.0,), refs=()):
    return FicheSignaux(id, f"fiche-{id}", couleur, genre, annee,
                        {t: set(e) for t, e in tailles.items()}, set(refs), list(prix))


def test_furygan_brooks_est_probable():
    a = _fiche(1, {"S": ["3435980372774"], "M": ["3435980372781"], "L": ["3435980372798"],
                   "4XL": ["3435980372835"]})
    b = _fiche(2, {"2XL": ["3435980372811"]})
    v = evaluer([a, b])
    assert v.note == "probable", v.raisons


def test_falco_meme_taille_ean_differents_est_a_refuser():
    a = _fiche(1, {"EU39": ["8055305930639"], "EU41": ["8055305930646"]})
    b = _fiche(2, {"EU39": ["8055305930363"], "EU41": ["8055305930370"]})
    v = evaluer([a, b])
    assert v.note == "refuser"
    assert any("même taille" in r for r in v.raisons)


def test_un_code_barres_partage_et_une_couleur_identique_font_un_groupe_sur():
    a = _fiche(1, {"M": ["3435980372781"]})
    b = _fiche(2, {"M": ["3435980372781"], "L": ["3435980372798"]})
    assert evaluer([a, b]).note == "sur"


def test_mat_et_brillant_sont_deux_produits():
    a = _fiche(1, {"M": ["3435980372781"]}, couleur="BK|MAT")
    b = _fiche(2, {"L": ["3435980372798"]}, couleur="BK|GLO")
    assert evaluer([a, b]).note == "refuser"


def test_un_genre_ou_une_annee_differents_sont_un_veto():
    base = {"M": ["3435980372781"]}
    assert evaluer([_fiche(1, base, genre="H-A"), _fiche(2, {"L": ["3435980372798"]}, genre="F-A")]).note == "refuser"
    assert evaluer([_fiche(1, base, annee=2023), _fiche(2, {"L": ["3435980372798"]}, annee=2026)]).note == "refuser"


def test_des_prix_a_plus_de_trois_fois_sont_un_veto_et_a_plus_de_un_virgule_cinq_un_doute():
    a = _fiche(1, {"M": ["3435980372781"]}, prix=(100.0,))
    assert evaluer([a, _fiche(2, {"L": ["3435980372798"]}, prix=(400.0,))]).note == "refuser"
    assert evaluer([a, _fiche(2, {"L": ["3435980372798"]}, prix=(200.0,))]).note == "douteux"


def test_une_couleur_inconnue_laisse_le_doute():
    a = _fiche(1, {"M": ["3435980372781"]}, couleur="")
    b = _fiche(2, {"L": ["3435980372798"]}, couleur="BK")
    assert evaluer([a, b]).note == "douteux"
