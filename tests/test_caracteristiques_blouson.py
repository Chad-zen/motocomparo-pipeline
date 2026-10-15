"""Les pièges du rayon blousons, trouvés en relisant l'échantillon.

Même leçon que pour le casque, et il a fallu la réapprendre : AUCUN de ces
défauts n'était visible dans un taux de couverture, et la plupart le FAISAIENT
MONTER. Ils ressemblaient tous à une bonne nouvelle.

Chaque test est bâti sur une phrase RÉELLE, copiée d'une description marchande
de l'échantillon. Aucune n'a été inventée pour l'occasion : une phrase inventée
teste ce qu'on a imaginé, pas ce que les marchands écrivent.
"""

from __future__ import annotations

import html
from pathlib import Path

from mcpipe.caracteristiques.blouson import Blouson, fusionner, lire


# =============================================================================
# 1. « PRÉDISPOSÉ » N'EST PAS « FOURNI », et ici la marque vient APRÈS
# =============================================================================

def test_poche_pour_dorsale_n_est_pas_une_dorsale():
    """LE piège du rayon, et il est plus vicieux que sur le casque.

    Un blouson Motoblouz sur trois annonce « Poche pour protection dorsale » et
    rien de plus. Une poche vide n'est pas une protection. Motoblouz lui-même
    compte 287 dorsales incluses contre 1 291 optionnelles : un extracteur qui
    trouve beaucoup d'« incluse » s'est fait avoir."""
    for phrase in (
        "Poche pour protection dorsale disponible en option, Fanom BFB-2",
        "Poche pour protection dorsale LS2 en option",
        "Poche pouvant accueillir une dorsale disponible ici en option",
        "Poche dédiée pour protecteur dorsal avec protecteur dos R.I.S.C. "
        "disponible séparément",
    ):
        assert lire("", phrase).dorsale == "option-poche", phrase


def test_marque_d_option_placee_apres_la_piece():
    """`casque.py` ne regardait que les quarante signes d'AVANT le mot.

    Sur un blouson, la moitié des marques de préparation SUIVENT la pièce :
    « en option », « non fournie », « vendues séparément ». Une garde qui ne
    regarde qu'en amont ne voit rien, et elle se tait : la couverture d'« incluse »
    monte, et c'est justement ce qui rassure à tort."""
    t = ("Poche dédiée pour protection dorsale prévue et protection dorsale "
         "non fournie pour permettre l'ajout d'une dorsale adaptée")
    assert lire("", t).dorsale == "option-poche"

    t = "Protection dorsale certifiées CE EN 1621-2:2014, en option"
    assert lire("", t).dorsale == "option-predisposee"


def test_les_deux_points_d_une_norme_ne_coupent_pas_la_phrase():
    """Corollaire du test précédent, et il a failli passer inaperçu.

    On découpe les descriptions sur la ponctuation pour qu'une garde ne déborde
    pas sur la phrase voisine. Mais « EN 1621-2:2014, en option » porte un
    deux-points ENTRE DEUX CHIFFRES : couper là aurait jeté le « en option »
    dans un autre segment, et rendu « incluse » une dorsale qui ne l'est pas."""
    assert lire("", "Protection dorsale certifiées CE EN 1621-2:2014, en option"
                ).dorsale != "incluse"


def test_predisposition_sans_poche_annoncee():
    """L'autre moitié du rayon dit « prédisposé », sans parler de poche. Les
    deux états sont distingués parce que le facettage du site les distingue."""
    for phrase in (
        "Prédisposé à recevoir une protection dorsale ALPHA homologuée CE",
        "Prédisposition pour le placement de la protection dorsale CE",
        "Compatible protection dorsale SEESOFT CE de Niveau 2",
    ):
        assert lire("", phrase).dorsale == "option-predisposee", phrase


def test_livre_avec_veut_bien_dire_incluse():
    """L'inverse doit rester vrai, sinon la garde ne sert qu'à tout refuser et
    le champ ne vaut plus rien."""
    for phrase in (
        "Livré avec une protection dorsale Homologuée CE (inclus)",
        "Protection dorsale amovible homologuée CE incluse",
    ):
        assert lire("", phrase).dorsale == "incluse", phrase


# =============================================================================
# 2. UNE PIÈCE N'EST PAS L'AUTRE
# =============================================================================

def test_la_doublure_n_est_pas_la_coque():
    """Le « visière en polycarbonate » du rayon blouson, et son défaut le plus
    fréquent : un blouson est fait de six matières et le marchand les énumère
    toutes dans le même paragraphe.

    Cas réel, un blouson Helstons en cuir de bovin : « Doublure de confort
    complète (corps et bras), fabriquée en coton résistant à l'abrasion ». Le
    coton de la DOUBLURE le faisait classer « cuir-textile »."""
    t = ("Matière : En cuir de bovin, d'une épaisseur de 1,1 à 1,2 mm. "
         "Doublure de confort complète (corps et bras), fabriquée en coton "
         "résistant à l'abrasion et aux brûlures")
    assert lire("", t).matiere_coque == "cuir"


def test_la_doublure_en_mesh_n_est_pas_un_blouson_en_mesh():
    """« Doublure fixe en filet mesh » est la formule la plus répandue du
    rayon : chez Motoblouz, le mot « mesh » appartient à la doublure une fois
    sur deux."""
    t = ("Matière extérieure en cuir de vachette. Doublure fixe en filet mesh")
    assert lire("", t).matiere_coque == "cuir"


def test_la_phrase_voisine_ne_contamine_pas_les_epaules():
    """Ce qui a fait basculer tout le fichier vers un découpage en segments.

    « Protections homologuées CE de niveau 2 aux coudes et aux épaules. Poche
    prévue pour protection dorsale (en option). » Avec une simple fenêtre de
    soixante signes, le « en option » de la DORSALE retombait sur les ÉPAULES,
    qui étaient pourtant bien dans le carton."""
    t = ("Protections homologuées CE de niveau 2 aux coudes et aux épaules. "
         "Poche prévue pour protection dorsale (en option).")
    b = lire("", t)
    assert b.protections_epaules == "fournies"
    assert b.protections_coudes == "fournies"
    assert b.dorsale == "option-poche"


def test_les_phrases_collees_de_motoblouz_sont_bien_des_phrases():
    """Motoblouz publie des descriptions dont l'espace manque entre les
    phrases : « Protections épaules niveau 1Poche pour protection dorsale
    disponible en option ». Sans couper là, la description entière est une
    seule phrase de mille signes et toute garde de voisinage y est aveugle."""
    t = ("Protections coudes niveau 1Protections épaules niveau 1Poche pour "
         "protection dorsale disponible en option")
    b = lire("", t)
    assert b.protections_epaules == "fournies"
    assert b.dorsale == "option-poche"


def test_la_predisposition_dorsale_ne_deshabille_pas_les_coudes():
    """Le blouson qui a montré que la note du site était instable.

    Le Furygan Mistral Evo 3 et sa version dame, même vêtement et description
    jumelle, ressortaient l'un « protections coudes fournies » et l'autre
    « préparé ». Motoblouz colle ses phrases sans ponctuation, si bien que la
    prédisposition à recevoir une DORSALE tombait dans le même segment que
    des coudes et des épaules explicitement fournis et homologués.

    La version homme échappait au défaut par accident : elle écrivait
    « épaules&nbsp;D3O », et le point-virgule de l'entité HTML coupait le
    segment juste avant. Une réponse juste pour une mauvaise raison.
    """
    t = ("Protections: Protections coudes D3O homologuées CE Protections "
         "épaules D3O homologuées CE Prédisposé à recevoir une protection "
         "dorsale D3O homologuée CE")
    b = lire("", t)
    assert b.protections_coudes == "fournies"
    assert b.protections_epaules == "fournies"
    assert b.dorsale == "option-predisposee"


def test_les_deux_versions_du_meme_blouson_se_lisent_pareil():
    """Le symptôme, vu du visiteur : deux fiches du même vêtement ne peuvent
    pas porter deux lectures différentes parce qu'un marchand a écrit une
    entité HTML là où l'autre a mis une espace."""
    homme = ("Protections coudes D3O&reg; homologuées CE Protections "
             "épaules&nbsp;D3O&reg; homologuées CE Prédisposé à recevoir une "
             "protection dorsale")
    femme = ("Protections coudes D3O homologuées CE Protections épaules D3O "
             "homologuées CE Prédisposé à recevoir une protection dorsale")
    # `_lignes()` décode les entités avant d'appeler les extracteurs : on fait
    # ici ce que fait le lecteur de flux.
    a, b = lire("", html.unescape(homme)), lire("", femme)
    assert a.protections_coudes == b.protections_coudes == "fournies"
    assert a.protections_epaules == b.protections_epaules == "fournies"


def test_une_option_qui_suit_la_piece_la_qualifie_bien():
    """L'autre sens de la règle, qui ne doit pas se perdre en corrigeant le
    premier : « en option » placé APRÈS les pièces les qualifie vraiment."""
    b = lire("", "Protections épaules et coudes en option, vendues séparément")
    assert b.protections_epaules == "prepare"
    assert b.protections_coudes == "prepare"


def test_un_empiecement_n_est_pas_une_protection():
    """« Empiècements élastiques aux épaules et aux coudes pour une meilleure
    aisance » parle de COUPE. Sans exiger un mot de protection dans le même
    segment, tout blouson bien coupé devenait un blouson protégé."""
    t = "Empiècements élastiques aux épaules et aux coudes pour une meilleure aisance"
    b = lire("", t)
    assert b.protections_epaules is None and b.protections_coudes is None


def test_une_poche_impermeable_ne_rend_pas_le_blouson_impermeable():
    """Même piège, sur l'imperméabilité : « 4 poches extérieures imperméables »,
    « Système de fermeture labyrinthe étanche ». Le vêtement, lui, ne l'est
    pas forcément."""
    for phrase in (
        "4 poches extérieures imperméables et 2 poches intérieures",
        "Système de fermeture labyrinthe étanche",
        "2 poches extérieures, 1 poche zippée à l'intérieur, toutes scotchées "
        "imperméables",
    ):
        assert lire("", phrase).impermeable is None, phrase


# =============================================================================
# 3. UN GENRE N'EST PAS SON SOUS-GENRE
# =============================================================================

def test_une_membrane_generique_n_est_pas_du_gore_tex():
    """« Membrane imperméable et respirante » reste générique. On ne remonte pas
    au Gore-Tex parce que le blouson est cher ou la marque haut de gamme."""
    b = lire("", "Membrane imperméable et respirante intégrée")
    assert b.membrane is True
    assert b.membrane_nom is None and b.gore_tex is None


def test_gore_tex_z_liner_n_est_pas_du_gore_tex_lamine():
    """Le facettage distingue « oui » de « oui, laminé », et le contraire du
    laminé porte un nom dans le rayon : le Z-Liner est la construction où la
    membrane est une DOUBLURE, pas un tissu collé. Le lire « laminé » aurait
    été le même sur-classement que « thermoplastique » lu « polycarbonate »."""
    t = ("Blouson textile Imola ST Gore-Tex, pouvant être porté toute l'année "
         "grâce à sa technologie GORE-TEX Z-Liner")
    assert lire("", t).gore_tex == "oui"

    assert lire("", "Matière: En textile laminé Gore-Tex").gore_tex == "oui-lamine"
    assert lire("", "GORE-TEX PRO stratifié 3 couches").gore_tex == "oui-lamine"


def test_deperlant_n_est_pas_impermeable():
    """Un traitement déperlant fait glisser l'averse cinq minutes ; il ne tient
    pas une heure d'autoroute sous la pluie. Deux vestes de l'échantillon
    n'avaient QUE ça — « fini hydrofuge », « Revêtement hydrofuge durable » —
    et aucune membrane."""
    for phrase in (
        "55/45 % coton/nylon, doublure en 100 % nylon, fini hydrofuge",
        "Veste légère de style anorak, revêtement hydrofuge durable",
        "En Softshell reconnu pour ses propriétés déperlante et coupe-vent",
    ):
        b = lire("", phrase)
        assert b.impermeable is None and b.membrane is None, phrase


def test_le_cuir_synthetique_n_est_pas_du_cuir():
    """Le mot y est, la matière n'y est pas. Relevé sur une combinaison :
    « 3D Air Mesh, cuir synthétique, nubuck artificiel, néoprène »."""
    t = "3D Air Mesh, cuir synthétique, nubuck artificiel, néoprène"
    assert lire("", t).matiere_coque == "textile"


def test_le_cuir_en_garniture_n_est_pas_un_blouson_en_cuir():
    """« 60 % Magnum Poly Denim, 37 % Tech Mesh, 3 % CUIR VÉRITABLE » : trois
    pour cent de cuir sur un blouson en denim. L'annoncer « cuir » le fait
    passer pour ce qu'il n'est pas, et le cuir est ce qui justifie l'écart de
    prix du rayon."""
    t = "60 % Magnum Poly Denim, 37 % Tech Mesh, 3 % cuir véritable"
    assert lire("", t).matiere_coque == "textile"


def test_l_homologue_en_cuir_est_un_autre_modele():
    """« Version tissu de son homologue EN CUIR, ce blouson épuré… » — le cuir
    est celui d'un AUTRE modèle du catalogue. Vu sur un blouson Helstons en
    tissu, que l'extracteur annonçait en cuir."""
    t = "Version tissu de son homologue en cuir, ce blouson épuré garde son élégance"
    assert lire("", t).matiere_coque != "cuir"


# -----------------------------------------------------------------------------
# 3 bis. LA MATIÈRE ÉCRITE QU'ON NE LISAIT PAS (relevé du 15/10/2026)
#
# 52 blousons visibles sans matière dans la base locale, 326 si l'on retire
# les textes FC-Moto. Chaque phrase ci-dessous vient de l'un d'eux : le
# marchand écrivait la matière, l'extracteur ne la voyait pas.
# -----------------------------------------------------------------------------

def test_le_denier_est_la_marque_d_un_tissu():
    """« 600D » est la masse d'un fil, et le mot n'existe que pour une fibre :
    671 occurrences dans le rayon, aucune sur un blouson tout cuir. Le second
    texte est collé à la rubrique suivante, comme Motoblouz les écrit."""
    for phrase in (
        "Matière: En matière 480 D x 640 D Tactel®Doublure aérée",
        "Matières: En fibre Tech 600DMembrane BWTECH CLASSICDoublure: Doublure "
        "SHELLTECH Super amovibleDoublure fixe en maille",
        "Matière: Polyfibre 450D avec renfort 600D dans les zones critiques",
    ):
        assert lire("", phrase).matiere_coque == "textile", phrase


def test_un_motif_3d_n_est_pas_un_denier():
    """La garde du motif précédent : un chiffre seul devant « D » n'est pas un
    fil. Relevé sur une Alpinestars AMT-8, dont le texte ne nomme AUCUNE
    matière — elle doit rester sans."""
    t = ("Matière: Veste de performance 100 % stretch hautement respirante pour "
         "une flexibilité et un confort inégalésNouveau motif ergonomique 3D "
         "conçu pour améliorer la flexibilité")
    assert lire("", t).matiere_coque is None


def test_les_noms_de_tissu_que_le_marchand_explique():
    """Serica, Twiltex, Tactel : des noms déposés, mais que les marchands
    expliquent eux-mêmes ailleurs dans le rayon (« En Serica, mix de coton
    sergé et de polyester », « tissu technique Twiltex 100% polyester »)."""
    for phrase in (
        "Matière: En TwiltexProtections: Protections coudes CE amovibles ALPHA",
        "Matière: Séricaétanchéité: Membrane étancheDoublure: Doublure thermo-alu",
        "Matière: En fibre Tactel® déperlant et respirantGilet doublure thermique",
        "Matière: En Dupont Kevlar et Tartan Polycoton offrant souplesse",
        "Matières: Construction en flannelDoublure: La doublure fixe en mesh",
        "Matière: Fabriquée en satin de haute qualité pour une finition élégante",
        "Matière: Fabriqué en taffetas matelassé avec une couche intérieure "
        "d'isolation rembourrée en polyester 100 % recyclé",
    ):
        assert lire("", phrase).matiere_coque == "textile", phrase


def test_le_satin_d_une_doublure_ne_fait_pas_un_cuir_textile():
    """Le satin est une coque sur un blouson Alpinestars, une doublure sur tous
    les blousons en cuir du rayon qui le nomment."""
    t = "* Matériau supérieur: cuir de buffle * Doublure: doublure en satin massif"
    assert lire("", t).matiere_coque == "cuir"


def test_le_jean_matiere_et_le_jean_pantalon():
    """« Veste moto en jean » est une matière. « Boucle permettant d'attacher
    votre jean » est un pantalon, et la formule est sur des dizaines de
    blousons, en cuir comme en textile."""
    assert lire("Veste Macna Inland Quilted Vert Marron - Blouson Moto MACNA",
                "Macna vous propose sa veste moto en jean pour homme"
                ).matiere_coque == "textile"
    t = ("Boucle située à l'arrière du blouson permettant d'attacher votre "
         "jean afin de l'empêcher de remonter")
    assert lire("", t).matiere_coque is None


def test_softshell_coupe_par_la_decoupe_des_phrases_collees():
    """« SoftShell » porte une majuscule au milieu : la découpe des phrases
    collées de Motoblouz y voyait deux phrases, « Soft » et « Shell ». Les
    quatre Spidi The Standard restaient sans matière, et la faute de frappe
    « Sofshell » (Bering Lady Rotor) aussi."""
    for phrase in (
        "Matières: En SoftShell multicouche élastique 3 couchesMembrane H2OUT",
        "Matières: SofshellMembrane étanche BWTECH SuperDoublure: Doudoune",
    ):
        assert lire("", phrase).matiere_coque == "textile", phrase


def test_une_marque_deposee_termine_une_phrase_collee():
    """« Doublure XTM-Fiber®Matière extérieure 100 % twill de nylon » : sans
    coupure après le ®, la doublure et la coque tenaient dans un seul segment,
    et la doublure, nommée la première, faisait taire le nylon."""
    t = ("Matière: Multistretch confortConstruction bicoucheDoublure "
         "XTM-Fiber®Matière extérieure 100 % twill de nylonImperméable")
    assert lire("", t).matiere_coque == "textile"


def test_cent_pour_cent_cuir_n_est_pas_une_garniture():
    """« 100 % cuir » se lisait « 00 % cuir », comme les « 3 % cuir
    véritable » d'un denim : deux blousons tout cuir restaient sans matière."""
    for phrase in (
        "Construction 100% cuir pleine fleur. Coupe cintrée style perfecto",
        "Matière: 100 % cuir de vachette perforé d'une épaisseur de 1,1-1,3 mm",
    ):
        assert lire("", phrase).matiere_coque == "cuir", phrase


def test_le_polyester_minoritaire_d_un_cuir_est_une_garniture():
    """L'inverse des « 3 % cuir » : dix pour cent de polyester sur un blouson
    en cuir sont l'extensible des soufflets. FC-Moto vend le même GS-1
    « Blouson de moto en cuir »."""
    for phrase in (
        "Cuir de vachette mat de haute qualité offrant une finition résistante "
        "pour un usage quotidien Composition 80% cuir, 10% polyester et 10% "
        "élastane",
        "Conception et matériaux Extérieur en 90% cuir nubuck et 10% polyester "
        "offrant une finition cuir résistante",
    ):
        assert lire("", phrase).matiere_coque == "cuir", phrase


def test_veste_a_capuche_n_est_pas_une_capuche():
    """« Veste de moto à capuche pour homme, réalisée en tissu Softshell » : la
    capuche qualifie la veste. Une capuche dont on donne la matière reste une
    capuche, et sa matière n'est pas celle du blouson."""
    t = ("Matière: Veste de moto à capuche pour homme, réalisée en tissu "
         "Softshell doux et dotée de grands panneaux en mesh")
    assert lire("", t).matiere_coque == "textile"
    t = "Capuche en nylon léger pliable intégrée au col"
    assert lire("", t).matiere_coque is None


def test_l_intitule_matiere_ouvre_une_nouvelle_rubrique():
    """Le nouveau format Motoblouz enchaîne les rubriques sans ponctuation.
    L'insert de la phrase d'avant effaçait le textile nommé en toutes
    lettres (Held Omberg)."""
    t = ("Conception et matériaux Insert Armarcor sur les zones d'impact pour "
         "renforcer la résistance à l'abrasion en cas de glissade Matière "
         "textile renforcée pour conserver la structure du vêtement")
    assert lire("", t).matiere_coque == "textile"


def test_la_matiere_interieure_est_une_doublure():
    """« Matière intérieure en mesh » sur un Ixon Cranky Air que Speedway et
    Moto-Axxe vendent tous deux « blouson en cuir ». Il ressortait
    « cuir-textile » à cause de sa doublure."""
    for phrase in (
        "Matières: En cuir de vachette semi-aniline perforé Matière intérieure "
        "en mesh pou une ventilation optimale",
        "Matière extérieure en Cuir de vachette semi-aniline perforé. Matière "
        "intérieure en Mesh pour une ventilation optimale.",
    ):
        assert lire("", phrase).matiere_coque == "cuir", phrase


def test_une_membrane_ou_un_lamine_ne_disent_pas_la_matiere():
    """Ce qui DOIT rester vide. « Laminé 3 couches », « Z-Liner solto-TEX »,
    « Membrane HydraDri » décrivent l'étanchéité, pas la coque, et aucun de ces
    textes ne nomme de tissu. Déduire « textile » de la membrane serait la
    déduction que le rayon refuse partout ailleurs."""
    for phrase in (
        "Matières: En matière PFC FreeLaminé 3 couchesDoublure: Doublure "
        "thermique amovible intégrale",
        "Matière: Stratifié Z-Liner 2 couches solto-TEX®Le matériau extérieur "
        "élastique iXS-Stretch optimise l'ajustement",
        "Matière: Léger, imperméable et respirant avec des matériaux "
        "extensibles pour la mobilitéMembrane HydraDri EVO",
        "Matière: Construction Laminée GORE-TEX PRO 3L : Offre une performance "
        "100% imperméable",
    ):
        assert lire("", phrase).matiere_coque is None, phrase


# =============================================================================
# 4. LES MOTS QUI EN CACHENT UN AUTRE
# =============================================================================

def test_ete_est_aussi_le_participe_passe_d_etre():
    """Le « ABS dans absorption » de ce rayon : la limite de mot est juste, le
    mot ne l'est pas.

    « 100 % vegan-friendly. Aucune substance animale n'A ÉTÉ utilisée dans le
    processus de fabrication » — deux blousons Ixon en cuir végane étaient
    annoncés « blouson d'été » sur la foi de cette phrase, qui parle de
    tannerie."""
    t = ("100 % vegan-friendly. Aucune substance animale n'a été utilisée dans "
         "le processus de fabrication")
    assert lire("", t).saison is None


def test_summer_est_une_marque_deposee():
    """« SUMMER Comfort System Lite ouvrant le long de la fermeture
    principale », sur une veste softshell « qui bloque le vent pour réduire la
    sensation de froid ». Dans un catalogue français, `summer` et `winter` sont
    presque toujours des noms de technologies, jamais la saison d'usage : les
    deux mots ont été sortis de la liste."""
    t = ("Ventilation et respirabilité Summer Comfort System Lite ouvrant le "
         "long de la fermeture principale pour générer un flux d'air ciblé")
    assert lire("", t).saison is None


def test_hiver_2025_est_un_nom_de_collection():
    """« Veste enduro Kenny BODYWARMER GRAPHIC HIVER 2025 » : c'est le nom de la
    collection, pas le climat d'usage."""
    assert lire("Veste enduro Kenny BODYWARMER GRAPHIC HIVER 2025",
                "Déperlant et respirant, tissu windstopper sur le devant").saison is None


def test_deux_saisons_dans_la_meme_phrase_n_en_font_aucune():
    """Le marchand n'a pas tranché, on ne tranche pas à sa place :

        « Membrane Raintex, idéale pour la MI-SAISON ET L'ÉTÉ, amovible »
        « pour ajouter de la CHALEUR sur les sorties FRAÎCHES et se défaire
           facilement EN ÉTÉ »

    Les deux étaient annoncés « été ». Ce sont des blousons de mi-saison."""
    for phrase in (
        "Membrane Raintex, idéale pour la mi-saison et l'été, amovible",
        "pour ajouter de la chaleur sur les sorties fraîches et se défaire "
        "facilement en été",
        "Concept deux couches combinant ventilation estivale et protection "
        "contre la pluie pour une utilisation élargie",
    ):
        assert lire("", phrase).saison is None, phrase


def test_absence_de_membrane_impermeable():
    """Le seul rayon où un marchand décrit ce qui MANQUE, et l'extracteur
    l'entendait à l'envers :

        « Absence de membrane imperméable la destine prioritairement aux
           conditions sèches et chaudes, elle n'est pas adaptée aux pluies
           prolongées. »

    On annonçait « membrane : oui, imperméable : oui » sur un blouson dont le
    marchand écrit qu'il ne faut pas rouler sous la pluie avec."""
    t = ("Imperméabilité et étanchéité Absence de membrane imperméable la "
         "destine prioritairement aux conditions sèches et chaudes, elle n'est "
         "pas adaptée aux pluies prolongées")
    b = lire("", t)
    assert b.membrane is None and b.impermeable is None


def test_sans_compromettre_ne_nie_rien():
    """La garde de négation doit toucher le mot. « Sans COMPROMETTRE
    l'étanchéité » et « sans RETIRER les protections » sont plus nombreux dans
    le rayon que les vraies négations : une garde trop large aurait effacé la
    moitié du fichier en silence."""
    assert lire("", "Doublure thermique amovible sans manches 80g"
                ).doublure_thermique is True


def test_une_membrane_en_option_n_est_pas_une_membrane():
    """L'angle mort de la première version : la MEMBRANE aussi se vend à part.

        « Prédisposition pour la doublure H2OUT optionnelle »
        « arrangement pour la doublure thermo facultative et la doublure de
           H2Out »

    L'extracteur annonçait un blouson étanche H2Out sur les deux."""
    for phrase in (
        "Prédisposition pour la doublure H2OUT optionelle",
        "arrangement pour la doublure thermo facultative (L30 homme) et la "
        "doublure de H2Out (homme de X47)",
    ):
        b = lire("", phrase)
        assert b.membrane is None and b.membrane_nom is None, phrase
        assert b.doublure_thermique is None, phrase


# =============================================================================
# 5. EN 17092 : LA CARACTÉRISTIQUE LA PLUS UTILE DU RAYON
# =============================================================================

def test_le_numero_de_partie_encode_la_classe():
    """Partie 2 = AAA, 3 = AA, 4 = A, 5 = B, 6 = C. Les marchands écrivent
    souvent la partie sans la classe, et l'information est là."""
    assert lire("", "Homologué CE EN 17092-4:2020, classe A"
                ).classe_protection == "A"
    assert lire("", "Combinaison certifiée selon EN 17092-3:2020 (AA)"
                ).classe_protection == "AA"
    assert lire("", "Homologué CE Catégorie II EN 17092-4: 2020 standard"
                ).classe_protection == "A"
    assert lire("", "Vêtements de protection pour motocyclistes, classe de "
                    "protection AA (EN 17092-3:2020)").classe_protection == "AA"


def test_categorie_II_et_niveau_1_ne_sont_pas_la_classe():
    """Trois nombres se promènent dans la même phrase que la classe du
    vêtement : le TYPE de protection (EN 1621), son NIVEAU d'absorption, et la
    CATÉGORIE d'EPI. Les confondre invente une homologation de sécurité.

        « Combinaison certifiée CE selon la norme prEN17092 CATÉGORIE II
           classe AA »
        « Protections Fanom sur les coudes et aux épaules TYPE A NIVEAU 1 »"""
    assert lire("", "Combinaison certifiée CE selon la norme prEN17092 "
                    "catégorie II classe AA").classe_protection == "AA"
    b = lire("", "Protections Fanom sur les coudes et aux épaules type A niveau 1")
    assert b.classe_protection is None and b.norme_en17092 is None


def test_la_norme_sans_la_classe_est_une_reponse():
    """La quatrième valeur du facettage. « Certifié CE, conforme à la norme
    EN 17092 » sans classe : on affirme la norme, on n'invente pas la classe.
    Un vêtement certifié EN 17092 n'est pas un AA, comme un casque
    « thermoplastique » n'était pas un polycarbonate."""
    b = lire("", "Modèle certifié CE, conforme à la norme EN 17092")
    assert b.norme_en17092 is True and b.classe_protection is None


def test_la_classe_collee_a_la_norme():
    """« Référencé EN17092 A pour conformité aux exigences de protection des
    vêtements moto » — pas de partie, pas le mot « classe », et l'information
    est quand même là."""
    assert lire("", "Référencé EN17092 A pour conformité aux exigences"
                ).classe_protection == "A"


# =============================================================================
# 6. LE ZIP DE LIAISON, ET CE QUI LUI RESSEMBLE
# =============================================================================

def test_zip_de_liaison_au_pantalon():
    """Les formules réelles du rayon, toutes relevées telles quelles."""
    for phrase in (
        "Zip de raccordement Blouson/Pantalon",
        "Zip de connexion blouson/pantalon 270°",
        "une fermeture éclair pour relier le blouson au pantalon",
        "Pattes de raccordement blouson et pantalon",
    ):
        assert lire("", phrase).zip_liaison_pantalon is True, phrase


def test_une_vente_croisee_n_est_pas_un_zip_de_liaison():
    """Sans exiger les trois morceaux — un dispositif, un raccord, le pantalon —
    on attrapait deux phrases qui ne parlent pas de ça du tout :

        « Nous vous conseillons d'ASSOCIER cette veste AU PANTALON FREEWAY »
        « Ce RACCORD vous permet de mettre à niveau votre blouson avec le
           GILET Connector NEON »"""
    for phrase in (
        "Nous vous conseillons d'associer cette veste au pantalon FREEWAY pour "
        "un équipement moto complet",
        "Ce raccord vous permet de mettre rapidement à niveau votre blouson "
        "avec le gilet Connector NEON",
    ):
        assert lire("", phrase).zip_liaison_pantalon is None, phrase


# =============================================================================
# 7. L'UNIVERS DE PRATIQUE : deux pièges, et un taux de couverture assumé
# =============================================================================

def test_un_modele_qui_s_appelle_roadster_n_est_pas_un_univers():
    """Le mot est là, l'usage n'y est pas. « RST Blade Sport II », « IXS Sport
    RS-600 », « RST Roadster II » : un blouson qui s'appelle Roadster n'est pas
    un blouson de roadster."""
    assert lire("Blouson textile RST Blade Sport II blanc- 60",
                "Le blouson RST Blade II présente des sliders d'épaules").univers is None
    assert lire("IXS Sport RS-600 1.0 Veste en cuir de moto",
                "ajustement de tournée sportive, cuir de vache").univers is None


def test_une_coupe_sportive_n_est_pas_un_blouson_de_sport():
    """« Coupe pensée pour la position sportive », « aux lignes sportives » :
    on parle de la coupe, pas de la moto."""
    t = ("Coupe pensée pour la position sportive afin de conserver de la "
         "précision de pilotage sur circuit")
    assert lire("", t).univers is None


def test_l_univers_accole_au_vetement_compte():
    """L'inverse doit marcher, sinon le champ ne vaut rien : « Blouson roadster
    en polyester haute ténacité », « veste femme adventure M-Njord »."""
    assert lire("", "Blouson roadster en polyester haute ténacité").univers == "roadster"
    assert lire("", "Ixon vous présente sa veste femme adventure M-Njord, "
                    "à la coupe fit").univers == "trail"


def test_sport_touring_ne_choisit_pas():
    """« Veste SPORT-TOURING rétro en cuir de première qualité » : le circuit et
    le grand tourisme sont deux blousons différents, et deux cases différentes
    du configurateur. Le marchand n'a pas tranché."""
    assert lire("", "Veste sport-touring rétro en cuir de première qualité"
                ).univers is None


# =============================================================================
# 8. LA RÈGLE QUI PRIME, ET LA FUSION
# =============================================================================

def test_le_doute_rend_rien():
    """En cas de doute, `None`. Un `None` n'écrit aucune ligne en base."""
    vide = lire("", "")
    assert vide.renseignees() == 0
    assert vide.matiere_coque is None and vide.dorsale is None


def test_aucun_booleen_ne_vaut_jamais_False():
    """Aucun marchand n'écrit jamais qu'une caractéristique est ABSENTE : il se
    tait. Rendre `False` prétendrait que le texte AFFIRME l'absence, et le
    silence d'un marchand qui écrit soixante-seize signes ne prouve rien."""
    b = lire("Blouson Ixon Prodigy Noir", "Ixon vous propose son blouson le Prodigy")
    for champ in ("ventilations", "membrane", "impermeable", "poche_dorsale",
                  "doublure_thermique", "elements_reflechissants",
                  "zip_liaison_pantalon"):
        assert getattr(b, champ) is not False, champ


def test_fusionner_abandonne_une_classe_contestee():
    """Deux marchands qui se contredisent sur une donnée de sécurité ne valent
    pas mieux qu'aucune source. La NORME, elle, survit : « certifié EN 17092 »
    reste vrai même quand la classe est disputée."""
    a = lire("", "Homologué CE EN 17092-4:2020, classe A")
    b = lire("", "Certifiée EN 17092-3:2020 de classe AA")
    out = fusionner([a, b])
    assert out.classe_protection is None
    assert out.norme_en17092 is True


def test_fusionner_garde_une_classe_unanime():
    a = lire("", "Homologué CE EN 17092-4:2020, classe A")
    b = lire("", "Référencé EN17092 A pour conformité")
    assert fusionner([a, b]).classe_protection == "A"


def test_fusionner_est_pessimiste_sur_la_dorsale():
    """Le marchand qui écrit le plus long n'est pas forcément celui qui a
    raison, et le coût des deux erreurs n'est pas le même : se tromper dans un
    sens fait perdre un filtre, se tromper dans l'autre fait rouler quelqu'un
    avec un dos nu qu'il croit protégé."""
    riche = lire("", "Protection dorsale amovible homologuée CE incluse")
    pauvre = lire("", "Poche pour protection dorsale en option")
    assert riche.dorsale == "incluse"
    assert fusionner([riche, pauvre]).dorsale == "option-poche"


def test_fusionner_de_rien_ne_rend_rien():
    assert fusionner([]).renseignees() == 0
    assert fusionner([Blouson(), Blouson()]).renseignees() == 0


# =============================================================================
# 9. LES LIMITES DE MOT, VÉRIFIÉES SUR LE FICHIER LUI-MÊME
# =============================================================================

def test_le_fichier_ne_contient_aucun_caractere_de_controle():
    """Le quatrième piège du rayon casque n'était pas une expression fausse,
    c'était une ÉCRITURE de fichier : les `\\b` des expressions régulières
    avaient été remplacés par des caractères de contrôle 0x08, invisibles à la
    lecture. `ABS` s'était mis à matcher « absorption », qui figure dans presque
    toutes les descriptions — tout le rayon serait devenu polycarbonate, et la
    couverture aurait bondi.

    Ce fichier-ci dépend de ses `\\b` au moins autant : sans eux, `A` matcherait
    n'importe quel mot et la classe EN 17092 deviendrait du bruit. On vérifie
    donc la source, pas seulement le comportement."""
    source = (Path(__file__).resolve().parents[1]
              / "src" / "mcpipe" / "caracteristiques" / "blouson.py")
    texte = source.read_text(encoding="utf-8")
    assert [c for c in texte if ord(c) < 9] == []


def test_la_classe_A_ne_matche_pas_n_importe_quel_mot():
    """Le symptôme qu'aurait donné une limite de mot perdue."""
    for phrase in (
        "Blouson de classe Affaires pour les longs trajets",
        "Coupe Regular Fit, col classique Velcro rehausse polyester",
        "Certifiée CE amovible aux épaules, excellente absorption des chocs",
    ):
        assert lire("", phrase).classe_protection is None, phrase
