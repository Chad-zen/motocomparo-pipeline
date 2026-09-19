"""Coller la bonne note sur le bon casque — et refuser de coller au hasard.

CE QUI SE JOUE ICI N'EST PAS UN TAUX DE COUVERTURE. Une fiche sans note affiche
moins de choses ; une fiche qui porte les cinq étoiles d'un autre modèle ment à
quelqu'un qui choisit un casque pour sa tête. Les deux coûtent le même effort à
produire et ne se ressemblent pas du tout.

Tous les titres ci-dessous sont de vrais titres marchands ou de vrais libellés
SHARP, et les couples piégeux (Exo-R1 contre Exo-R1 Evo) existent bel et bien
tous les deux au catalogue SHARP, testés séparément.
"""

from __future__ import annotations

from mcpipe.sources.rapprochement import Candidat, _contient, _jetons, choisir


def _c(marque: str, modele: str) -> Candidat:
    return Candidat(slug=f"{marque}-{modele}".lower().replace(" ", "-"),
                    marque=marque, modele=modele, jetons=_jetons(modele),
                    valeurs={"note_securite": "5"})


# --- la ponctuation des marchands ---------------------------------------------

def test_le_modele_se_lit_en_jetons_pas_en_caracteres():
    """SHARP écrit « K7 », Motoblouz « K-7 », FC-Moto « K 7 ». Les trois
    désignent le même casque et doivent donner la même chose."""
    assert _jetons("K7") == _jetons("K-7") == _jetons("K 7") == ["k", "7"]
    assert _jetons("Exo-R1 Evo") == ["exo", "r", "1", "evo"]


def test_les_accents_ne_separent_pas_deux_ecritures_du_meme_modele():
    assert _jetons("Vector Évo") == _jetons("Vector Evo")


def test_un_modele_se_retrouve_au_milieu_du_titre():
    assert _contient(_jetons("Casque intégral AGV K-7 Mono Noir Mat"), _jetons("K7"))


def test_un_modele_absent_ne_se_retrouve_pas():
    assert not _contient(_jetons("Casque intégral AGV K-7 Mono"), _jetons("K6"))


# --- LE piège du rayon : le modèle prolongé -----------------------------------

def test_le_modele_prolonge_ne_prend_pas_la_note_du_modele_court():
    """« exor1 » est contenu dans « exor1evo » : un rapprochement par simple
    présence du texte collait la note de l'Exo-R1 à l'Exo-R1 Evo. Ce sont deux
    casques différents, testés séparément par le laboratoire."""
    candidats = [_c("Scorpion", "Exo-R1 Evo"), _c("Scorpion", "Exo-R1")]
    choisi = choisir("Casque Scorpion Exo-R1 Evo Air Onyx", candidats)
    assert choisi is not None and choisi.modele == "Exo-R1 Evo"


def test_le_modele_court_garde_la_sienne():
    """Le symétrique, et il compte autant : sans lui, la règle du plus long
    pourrait refuser tout rapprochement dès qu'une déclinaison existe."""
    candidats = [_c("Scorpion", "Exo-R1 Evo"), _c("Scorpion", "Exo-R1")]
    choisi = choisir("Casque Scorpion Exo-R1 Air Solid", candidats)
    assert choisi is not None and choisi.modele == "Exo-R1"


def test_une_coque_carbone_n_herite_pas_de_la_note_de_la_coque_normale():
    """Ces deux tests-ci disaient « Exo-R1 Evo CARBON » avant que la garde de
    prolongement n'existe, et ils sont tombés le jour où elle est arrivée. Ils
    avaient tort, pas elle : une calotte carbone est une AUTRE structure, et
    SHARP teste des structures. Le cas est donc gardé, mais dans l'autre sens.

    SHARP l'atteste lui-même côté Shark : « Spartan » et « Spartan Carbon » sont
    deux fiches distinctes, comme « Spartan GT » et « Spartan GT Carbon »."""
    candidats = [_c("Scorpion", "Exo-R1 Evo")]
    assert choisir("Casque Scorpion Exo-R1 Evo Carbon Air Onyx", candidats) is None


def test_une_egalite_ne_se_tranche_pas():
    """Deux modèles de même longueur qui collent au même titre : c'est le cas
    où un rapprochement automatique se trompe une fois sur deux. On ne rend
    rien, et la fiche reste muette."""
    candidats = [_c("HJC", "C10"), _c("HJC", "C 10")]
    assert choisir("Casque intégral HJC C10 ASPA", candidats) is None


def test_un_titre_sans_aucun_modele_connu_ne_rend_rien():
    assert choisir("Casque intégral Bogotto V128", [_c("Shoei", "NXR 2")]) is None


# --- ce qu'on refuse de rapprocher --------------------------------------------

def test_un_modele_fait_de_mots_trop_communs_n_est_pas_un_candidat():
    """« Carbon », « Sport », « Air » se retrouvent dans des centaines de titres
    du rayon. Un modèle SHARP réduit à ces seuls mots rapprocherait n'importe
    quoi — et la note irait à des casques jamais testés.

    La garde est en amont, dans `_candidats` : un tel modèle n'entre jamais dans
    la liste. Ce test vérifie le CRITÈRE, puisque la liste, elle, vient de la
    base."""
    from mcpipe.sources.rapprochement import _TROP_COMMUN
    trop_commun = lambda m: set(_jetons(m)) <= _TROP_COMMUN     # noqa: E731
    assert trop_commun("Carbon")
    assert trop_commun("Sport Air")
    assert not trop_commun("NXR 2")
    assert not trop_commun("Exo-R1 Evo")


def test_la_marque_ne_depend_pas_de_son_ecriture():
    """SHARP écrit « Scorpion Exo », la base range « scorpion » ; SHARP écrit
    « MT Helmets », la base « mt ». La comparaison se fait sur les jetons collés,
    donc sans dépendre des espaces ni de la casse."""
    from mcpipe.sources.rapprochement import _marque
    assert _marque("AGV") == "agv"
    assert _marque("Scorpion Exo") == "scorpionexo"
    assert _marque("LS2") == "ls2"


# --- ce qui se vend dans le rayon sans etre un casque -------------------------

def test_une_piece_de_rechange_ne_prend_pas_la_note_du_casque():
    """162 rapprochements sur 1 995, a la premiere relecture. Une mentonniere a
    25 euros qui affiche « 4 etoiles au test de choc » est un contresens
    dangereux — et d'autant plus credible qu'elle porte le vrai nom d'un vrai
    casque teste."""
    from mcpipe.sources.rapprochement import est_un_casque
    assert not est_un_casque(
        "Mentonniere HJC RPHA 90S SF Blanc Perle - Pieces detachees casque moto HJC")
    assert not est_un_casque("Shark Evoline Pare-soleil")
    assert not est_un_casque("Icon Airflite Aileron arriere Miroir")
    assert not est_un_casque("Coiffe De Casque AGV Pista GP RR Gris Bleu")


def test_un_casque_livre_avec_son_ecran_reste_un_casque():
    """LA POSITION TRANCHE, PAS LA PRESENCE. Une exclusion sur le seul mot
    « ecran » aurait ecarte de vrais casques vendus avec un ecran de rechange."""
    from mcpipe.sources.rapprochement import est_un_casque
    assert est_un_casque("Casque integral Shark SKWAL i3 - MAYFER + ECRAN IRIDIUM ROSE")
    assert est_un_casque("Casque integral Arai QUANTIC - SUPRA")


# --- la forme du casque, verifiee contre SHARP lui-meme -----------------------

def test_sharp_n_a_jamais_teste_de_jet_ni_de_cross():
    """Sur 585 fiches : 442 integraux, 142 modulables, rien d'autre. Une fiche
    rangee en jet ou en cross qui recoit une note est donc fausse PAR
    CONSTRUCTION — c'est le cas du « Shark Skwal Jet », qui heritait de la note
    du Skwal, lequel est un integral."""
    from mcpipe.sources.rapprochement import type_compatible
    assert not type_compatible(3, "Full face")          # jet
    assert not type_compatible(5, "Full face")          # cross
    assert not type_compatible(3, "System (Modular/Flip-up)")


def test_un_modulable_ne_prend_pas_la_note_d_un_integral():
    """Les constructeurs reemploient leurs noms d'une forme a l'autre, et ce
    sont deux structures differentes : c'est justement la mentonniere qui
    change."""
    from mcpipe.sources.rapprochement import type_compatible
    assert type_compatible(2, "Full face")
    assert type_compatible(4, "System (Modular/Flip-up)")
    assert not type_compatible(2, "System (Modular/Flip-up)")
    assert not type_compatible(4, "Full face")


def test_le_rayon_parent_ne_bloque_pas_le_rapprochement():
    """`helmet` (id 1) est la categorie des fiches dont on n'a pas su dire la
    forme. Lui refuser la note punirait une fiche mal rangee, pas un
    rapprochement douteux."""
    from mcpipe.sources.rapprochement import type_compatible
    assert type_compatible(1, "Full face")
    assert type_compatible(1, "System (Modular/Flip-up)")


def test_une_forme_que_sharp_ne_sait_pas_nommer_est_refusee():
    from mcpipe.sources.rapprochement import type_compatible
    assert not type_compatible(2, "Non-protective lower faceguard")
    assert not type_compatible(2, None)


# --- LE defaut de fond : le modele prolonge au-dela de ce que SHARP connait ---

def test_une_version_que_sharp_n_a_pas_testee_ne_recupere_pas_l_ancienne():
    """« Le plus long gagne » ne protege que des modeles que SHARP CONNAIT. Le
    vrai danger est ailleurs : le titre nomme une version jamais testee, et le
    rapprochement retombe sur l'ancienne. Cinq cas releves a la troisieme
    relecture, aucun au catalogue SHARP — donc aucun ne pouvait se trancher
    entre candidats, il n'y en avait qu'un et il etait faux."""
    assert not _contient(_jetons("Casque HJC C91N Solid"), _jetons("C91"))
    assert not _contient(_jetons("Casque Shark D-SKWAL 3 SPEED-VIB"), _jetons("D-Skwal"))
    assert not _contient(_jetons("Casque Shark SKWAL CUP RACEBLOCK"), _jetons("Skwal"))
    assert not _contient(_jetons("Casque Shoei NEOTEC 3 CHALK"), _jetons("Neotec"))
    assert not _contient(_jetons("Casque Shoei NXR2 - HATSUNE MIKU"), _jetons("NXR"))
    assert not _contient(_jetons("Shark Race-R Pro Carbon Replica"), _jetons("Race R Pro"))


def test_un_nom_de_coloris_ne_fait_pas_refuser_un_bon_rapprochement():
    """Le revers de la garde : une declinaison de COULEUR s'appelle « Supra »,
    « Blank », « Raceshop », « Nepos » — des noms qui ne ressemblent a rien
    d'une suite de modele. Sans ce test, durcir la garde ferait taire tout le
    rayon sans que rien ne le signale."""
    assert _contient(_jetons("Casque integral Arai QUANTIC - SUPRA"), _jetons("Quantic"))
    assert _contient(_jetons("Shark Spartan RS Blank Casque"), _jetons("SPARTAN RS"))
    assert _contient(_jetons("Casque integral HJC C10 - HAVEN"), _jetons("C10"))


def test_un_modele_en_fin_de_titre_passe():
    """Rien apres le modele : il n'y a rien qui puisse le prolonger."""
    assert _contient(_jetons("Casque integral Shoei NXR 2"), _jetons("NXR 2"))
    assert _contient(_jetons("Schuberth C5"), _jetons("C5"))


def test_le_tiret_du_constructeur_ne_separe_pas_deux_modeles():
    """SHARP ecrit « RX7 V EVO », les marchands « RX-7V EVO ». Une premiere
    lecture m'a fait croire a un faux positif : les deux sont le meme casque, et
    c'est exactement ce que la comparaison par jetons est la pour voir."""
    assert _jetons("RX7 V EVO") == _jetons("RX-7V EVO") == ["rx", "7", "v", "evo"]
    assert _contient(_jetons("Casque integral Arai RX-7V EVO - SCHWANTZ 30"),
                     _jetons("RX7 V EVO"))
