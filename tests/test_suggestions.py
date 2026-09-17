"""La barre de recherche : ce qu'elle propose, et dans quel ordre.

L'assemblage est une fonction pure — elle reçoit la matière et rend la liste —
précisément pour être éprouvée sans base de données. C'est aussi ce qui permet
de fixer les règles de classement, qui sont des décisions et non des hasards.
"""

from __future__ import annotations

from mcsite import suggestions


def _nom(p):
    return p.get("model_display") or ""


MATRICE = [
    {"marque": "arai", "rayon_id": 1, "rayon_code": "helmet.integral",
     "rayon": "Casques intégraux", "n": 94},
    {"marque": "arai", "rayon_id": 2, "rayon_code": "helmet.cross",
     "rayon": "Casques cross", "n": 15},
    {"marque": "barracuda", "rayon_id": 3, "rayon_code": "bodywork",
     "rayon": "Carénage", "n": 40},
    {"marque": "shoei", "rayon_id": 1, "rayon_code": "helmet.integral",
     "rayon": "Casques intégraux", "n": 60},
    # « marauder » contient « ara » EN MILIEU de mot : c'est le cas qui départage
    # les deux classements. « barracuda », lui, ne le contient pas — b-a-r-r-a —
    # et servait de contre-exemple à un test qui se trompait de prémisse.
    {"marque": "marauder", "rayon_id": 3, "rayon_code": "bodywork",
     "rayon": "Carénage", "n": 7},
]
RAYONS = [
    {"id": 1, "code": "helmet.integral", "label_fr": "Casques intégraux"},
    {"id": 9, "code": "gloves", "label_fr": "Gants"},
]


def _c(texte, produits=()):
    return suggestions.construire(texte, MATRICE, RAYONS, list(produits), _nom)


def test_sous_deux_caracteres_on_ne_propose_rien():
    """Tout correspond à une lettre : la liste serait l'alphabet des marques,
    et la base travaillerait pour rien."""
    for court in ("", "a", " a "):
        d = _c(court)
        assert d["marques"] == [] and d["entonnoir"] == []
        assert d["rayons"] == [] and d["produits"] == []
        assert d["meilleurs"] == []


def test_l_entonnoir_s_ouvre_sur_la_marque_tapee():
    d = _c("arai")
    assert [e["rayon"] for e in d["entonnoir"]] == ["Casques intégraux", "Casques cross"]
    assert [e["n"] for e in d["entonnoir"]] == [94, 15]
    assert all(e["marque"] == "arai" for e in d["entonnoir"])


def test_les_rayons_de_l_entonnoir_vont_du_plus_fourni_au_moins_fourni():
    """Un entonnoir qui commence par le rayon le plus maigre fait perdre le
    temps qu'il est censé faire gagner."""
    d = _c("arai")
    compte = [e["n"] for e in d["entonnoir"]]
    assert compte == sorted(compte, reverse=True)


def test_le_debut_du_mot_pese_plus_que_le_milieu():
    """« ara » cherche Arai, pas Barracuda — les deux sont proposés, dans cet
    ordre."""
    d = _c("ara")
    assert [m["marque"] for m in d["marques"]] == ["arai", "marauder"]


def test_l_entonnoir_ne_s_ouvre_pas_sur_une_correspondance_de_milieu():
    """Taper « rac » trouve Barracuda, mais ouvrir son entonnoir supposerait
    qu'on la cherchait — alors qu'on ne fait que passer."""
    d = _c("rac")
    assert [m["marque"] for m in d["marques"]] == ["barracuda"]
    assert d["entonnoir"] == []


def test_les_accents_ne_separent_pas():
    d = _c("integraux")
    assert [r["label"] for r in d["rayons"]] == ["Casques intégraux"]


def test_un_rayon_se_trouve_par_son_libelle():
    d = _c("gant")
    assert [r["code"] for r in d["rayons"]] == ["gloves"]


def test_la_ponctuation_est_recollee_comme_en_base():
    """La saisie doit être normalisée EXACTEMENT comme le texte indexé : la
    base contient « szr », donc « sz-r » doit devenir « szr » et non « sz »
    puis « r ». Soignée d'un côté et oubliée de l'autre, la symétrie ne sert à
    rien — quelqu'un qui tapait le nom AVEC son tiret ne trouvait rien."""
    assert suggestions.mots("arai sz-r") == ["arai", "szr"]
    assert suggestions.mots("shoei gt-air 3") == ["shoei", "gtair", "3"]
    assert suggestions.mots("Ixon Blanky") == ["ixon", "blanky"]
    assert suggestions.mots("") == []


def test_un_produit_garde_le_nom_qu_il_a_sur_sa_page():
    """Le même produit ne doit pas s'appeler autrement dans la liste que sur sa
    fiche : c'est la même fonction qui le nomme des deux côtés."""
    d = _c("arai", [{"slug": "a-b", "model_display": "Casque Arai Quantic",
                     "brand_code": "arai", "cheapest": 499.9, "merchant_count": 4,
                     "image_url": None}])
    assert d["meilleurs"][0]["nom"] == "Casque Arai Quantic"
    assert d["meilleurs"][0]["marque"] == "ARAI"
    assert d["meilleurs"][0]["prix"] == 499.9


def test_les_trois_premiers_passent_en_grand_format():
    """La requête rend les fiches déjà classées. Les trois premières sont mises
    en avant, les suivantes restent dans la liste — sans doublon entre les deux.

    Trois et non une : « arai szr » rend six SZ-R qui ne diffèrent que par la
    finition, et désigner un vainqueur reviendrait à cacher deux réponses aussi
    justes que lui."""
    fiches = [{"slug": f"s{i}", "model_display": f"Casque {i}", "brand_code": "arai",
               "cheapest": 100 + i, "merchant_count": 9 - i, "image_url": None}
              for i in range(6)]
    d = _c("arai", fiches)
    assert [p["slug"] for p in d["meilleurs"]] == ["s0", "s1", "s2"]
    assert [p["slug"] for p in d["produits"]] == ["s3", "s4", "s5"]


def test_moins_de_trois_fiches_ne_laisse_rien_derriere():
    """Deux résultats font deux mises en avant et une liste vide : mieux vaut
    une rubrique absente qu'une rubrique « Autres produits » sans produit."""
    fiches = [{"slug": f"s{i}", "model_display": f"Casque {i}", "brand_code": "arai",
               "cheapest": 100, "merchant_count": 3, "image_url": None}
              for i in range(2)]
    d = _c("arai", fiches)
    assert len(d["meilleurs"]) == 2
    assert d["produits"] == []


# --- la reconnaissance de marque, et les fautes de frappe -------------------

NOMS = ["arai", "shoei", "ixon", "alpinestars", "shark", "hjc"]


def test_la_marque_est_reconnue_telle_quelle():
    assert suggestions.reconnaitre_marque(["arai", "szr"], NOMS) == ("arai", ["szr"])


def test_un_debut_de_marque_suffit():
    assert suggestions.reconnaitre_marque(["alpin", "gant"], NOMS) == (
        "alpinestars", ["gant"])


def test_une_faute_de_frappe_est_rattrapee():
    """« arei » pour « arai » : une lettre d'écart. Les trigrammes n'y voient
    que 0,25 de ressemblance, une distance d'édition y voit une faute."""
    assert suggestions.reconnaitre_marque(["arei", "szr"], NOMS) == ("arai", ["szr"])


def test_une_inversion_de_lettres_aussi():
    """« shoie » pour « shoei » : la faute la plus courante au clavier. Sans le
    traitement des inversions, elle coûterait deux points et passerait à la
    trappe."""
    assert suggestions.reconnaitre_marque(["shoie"], NOMS) == ("shoei", [])


def test_un_mot_court_et_seul_n_est_pas_corrige():
    """« sz-r » tapé seul est un nom de modèle, pas une marque mal écrite — et
    il se trouve à une lettre de la marque SGR. Corrigé, il enverrait chez SGR
    quelqu'un qui cherche un casque Arai."""
    assert suggestions.reconnaitre_marque(["szr"], NOMS + ["sgr"]) == (None, ["szr"])
    assert suggestions.reconnaitre_marque(["hjd"], NOMS) == (None, ["hjd"])


def test_un_mot_court_accompagne_est_corrige():
    """« aai sz-r » : à côté d'un nom de modèle, le mot court est bien la
    marque, et c'est là qu'on rattrape la lettre oubliée."""
    assert suggestions.reconnaitre_marque(["aai", "szr"], NOMS) == ("arai", ["szr"])


def test_une_correction_ambigue_est_refusee():
    """Deux marques à une faute près : on se tait plutôt que de choisir à la
    place de quelqu'un qui n'a rien demandé."""
    assert suggestions.reconnaitre_marque(
        ["sgz", "casque"], ["sgr", "sga"]) == (None, ["sgz", "casque"])


def test_l_entonnoir_s_ouvre_meme_sur_une_marque_mal_tapee():
    """Quelqu'un qui tape « arei » n'a aucune marque commençant par « arei » —
    sans priorité à la marque reconnue, l'entonnoir resterait fermé alors qu'on
    sait très bien ce qu'il cherche."""
    d = suggestions.construire("arei", MATRICE, RAYONS, [], _nom, "arai")
    assert [e["rayon"] for e in d["entonnoir"]] == ["Casques intégraux", "Casques cross"]
    assert d["marque_reconnue"] == "arai"


# --- une marque tapée seule ------------------------------------------------

_FICHES = [{"slug": "s1", "model_display": "Casque Quantic", "brand_code": "arai",
            "cheapest": 500, "merchant_count": 5, "image_url": "https://x/y.jpg",
            # Les codes couleur sont stockés en MAJUSCULES : « bk » retombe sur
            # lui-même faute de correspondance, et le test passerait à côté.
            "colour_code": "BK"}]


def test_une_marque_seule_propose_la_marque_pas_un_produit():
    """« arai » seul ne désigne aucun casque : mettre trois Arai en avant, c'est
    en choisir trois au hasard parmi 147 et les présenter comme la réponse.
    Ce qu'on veut, c'est entrer chez Arai."""
    d = suggestions.construire("arai", MATRICE, RAYONS, _FICHES, _nom, "arai", [])
    assert d["marque_seule"]["marque"] == "arai"
    assert d["marque_seule"]["n"] == 94 + 15      # ses deux rayons
    assert d["meilleurs"] == []
    # les fiches restent proposées, mais en dessous et en petit
    assert len(d["produits"]) == 1


def test_la_marque_seule_emprunte_une_photo_a_son_catalogue():
    """Un nom de marque seul, dans une liste qui montre des produits partout
    ailleurs, fait un trou."""
    d = suggestions.construire("arai", MATRICE, RAYONS, _FICHES, _nom, "arai", [])
    assert d["marque_seule"]["image"] == "https://x/y.jpg"


def test_un_mot_de_plus_et_on_cherche_un_produit():
    """Dès qu'un mot accompagne la marque, les mises en avant reprennent leur
    sens."""
    d = suggestions.construire("arai quantic", MATRICE, RAYONS, _FICHES, _nom,
                               "arai", ["quantic"])
    assert d["marque_seule"] is None
    assert [p["slug"] for p in d["meilleurs"]] == ["s1"]


def test_la_couleur_departage_deux_fiches_du_meme_modele():
    """Trois « SZ-R VAS EVO - SOLID » ne diffèrent que par elle."""
    d = suggestions.construire("arai szr", MATRICE, RAYONS, _FICHES, _nom,
                               "arai", ["szr"])
    assert d["meilleurs"][0]["couleur"] == "noir"
