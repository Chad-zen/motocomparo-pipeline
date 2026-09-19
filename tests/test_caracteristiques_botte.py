"""Les pièges du rayon bottes, trouvés en relisant l'échantillon.

Chaque phrase de ce fichier est une VRAIE phrase de marchand, copiée depuis
l'échantillon du rayon (catégorie 9, 6 030 fiches décrites). Aucune n'a été
inventée pour faire passer un test : elles ont toutes fait échouer
l'extracteur avant de le faire réussir.

Comme sur les casques, les gants et les blousons, AUCUN de ces défauts n'était
visible dans un taux de couverture. Ils se répartissent en deux familles, et
les deux sont dangereuses pour des raisons opposées :

  — ceux qui FAISAIENT MONTER la couverture : une botte annoncée Gore-Tex sur
    la foi de la phrase qui dit qu'elle n'en a pas, une basket annoncée « cuir »
    sur la foi de sa doublure, une botte annoncée imperméable grâce à un
    chausson vendu séparément. Ceux-là ressemblent à une bonne nouvelle, et
    personne ne les cherche.

  — ceux qui la FAISAIENT BAISSER : soixante-dix-huit bottes réelles rendues
    VIDES parce qu'un `\\b` manquant faisait lire « resemel » dans
    « microfib-RE SEMEL-le ». Ceux-là finissent par se voir dans un total,
    mais seulement si on regarde la bonne ligne, et longtemps après.

Un extracteur se juge en lisant ses sorties, pas en regardant son taux de
remplissage.
"""

from __future__ import annotations

from pathlib import Path

from mcpipe.caracteristiques.botte import Botte, fusionner, lire


# =============================================================================
# 1. LE PIÈGE DU RAYON : une pièce n'est pas l'autre, et une botte en a huit
# =============================================================================

def test_la_doublure_n_est_pas_la_chaussure():
    """L'Acerbis X-TEAM ENFANT, une botte de cross en microfibre, ressortait
    « textile » — sur la foi de sa doublure.

    Les deux premières matières du texte étaient bien écartées : la guêtre et
    l'insert sont des pièces connues. La troisième ne l'était pas :
    « INTÉRIEUR EN 3D MESH pour un confort supérieur ». L'intérieur manquait à
    la liste des pièces, et c'est le piège du rayon dans sa forme la plus pure —
    une matière vraie, posée sur la mauvaise pièce.

    Motoblouz écrit d'ailleurs le même mot dans son bloc de composition :
    « Matière intérieure :100% polyester ».
    """
    t = ("Conception et matériaux Tige résistante aux coupures et à l'abrasion "
         "Guêtre et plis tibiaux en microfibre coupe douce Semelle en caoutchouc "
         "double densité Intérieur en 3D Mesh pour un confort supérieur")
    assert lire("Bottes cross Acerbis X-TEAM ENFANT", t).matiere is None


def test_la_semelle_n_est_pas_la_tige():
    """« Semelle en caoutchouc » ne dit pas que la chaussure est en caoutchouc,
    et « Doublure entière en cuir de vachette » ne dit pas qu'elle est en cuir.

    Le contre-exemple compte autant : une garde qui refuse tout ne garde rien.
    """
    assert lire("Bottes X", "Semelle extérieure en caoutchouc antidérapante "
                            "Semelle intérieure en PU amovible").matiere is None
    assert lire("Bottes X", "Matière: Tige en cuir de vachette épais et robuste "
                            "Doublure fixe en polyester").matiere == "cuir"
    assert lire("Bottes X", "Composition: Matière extérieure :100% cuir de "
                            "vachetteMatière intérieure :100% polyesterSemelle "
                            "extérieure :100% caoutchouc").matiere == "cuir"


def test_le_cuir_microfibre_n_est_pas_du_cuir():
    """Le sous-genre CONTREDIT le genre, et le marchand se contredit lui-même
    dans la même fiche.

    La DXR CODE EVO SHORT écrit « Matière: Tige en CUIR MICROFIBRE SYNTHÉTIQUE,
    matière solide et durable » en haut de page, et « Composition: Matière
    extérieure :100% POLYURÉTHANE » en bas. L'extracteur rendait « cuir »,
    parce que « cuir » est écrit avant « microfibre » et que l'ordre rendu est
    celui du texte.

    Onze occurrences du rayon sont dans ce cas — « cuir microfibre », « cuir PU
    et microfibre », « cuir microfibre synthétique aussi résistant que du cuir
    véritable ». Le mot « cuir » y est un adjectif de texture, et il vaut cent
    euros de fiche.
    """
    assert lire("Demi-bottes DXR CODE EVO SHORT",
                "Matière: Tige en cuir microfibre synthétique, matière solide "
                "et durable").matiere == "synthétique"
    assert lire("Baskets G-FORCE 2 H2O",
                "Baskets moto. En cuir PU et microfibre assurent souplesse et "
                "confort.").matiere == "synthétique"
    assert lire("Bottes RST PATHFINDER WP",
                "Matière: En cuir microfibre reconnu pour sa "
                "résistance").matiere == "synthétique"
    # Et le cuir qui en est reste du cuir.
    assert lire("Demi bottes Oscar", "en cuir pleine fleur").matiere == "cuir"


def test_le_cuir_cite_pour_dire_qu_il_n_y_en_a_pas():
    """La figure de style du rayon, chez Bering, RST et Alpinestars :
    « En microfibre, matière synthétique reconnue pour être AUSSI RÉSISTANT QUE
    LE CUIR NATUREL ». Le mot « cuir » y dit exactement le contraire de ce
    qu'une recherche de mot y lit."""
    t = ("Bottes moto racing. En microfibre, matière synthétique reconnue pour "
         "être aussi résistant que le cuir naturel. Membrane étanche.")
    assert lire("Bottes S1 WATERPROOF RST", t).matiere == "synthétique"


def test_le_chausson_en_option_ne_rend_pas_la_botte_impermeable():
    """Deux défauts dans la même phrase, et c'est la Forma qui les écrit :

        « Doublure: Doublure intérieure rembourrée POSSIBILITÉ D'INTÉGRER EN
          OPTION un CHAUSSON amovible et remplaçable en Drytex, ÉTANCHE et
          respirant (ref FM0128) »

    Le chausson est une PIÈCE, et il est EN OPTION. La botte ressortait
    imperméable : elle ne l'est pas, elle peut le devenir contre un achat
    supplémentaire. La réserve est à cinquante-cinq signes du mot « étanche »,
    trop loin pour l'ancienne fenêtre de quarante.
    """
    t = ("Doublure: Doublure intérieure rembourrée Possibilité d'intégrer en "
         "option un chausson amovible et remplaçable en Drytex, étanche et "
         "respirant (ref FM0128) Protections: Protections malléole thermoformée")
    lu = lire("Bottes Forma X", t)
    assert lu.impermeable is None
    assert lu.membrane is None


def test_la_fermeture_etanche_n_est_pas_une_botte_etanche():
    """Le premier cas du genre, gardé parce qu'il reste vrai : « Guêtre
    néoprène : crée une FERMETURE ÉTANCHE en haut de la botte » sur une botte
    de piste sans la moindre membrane."""
    assert lire("Bottes XP9-R", "Guêtre néoprène : crée une fermeture étanche "
                                "en haut de la botte").impermeable is None
    # …et la membrane annoncée dans la doublure, elle, reste l'imperméabilité
    # de la botte entière. La doublure n'est pas une pièce à écarter.
    lu = lire("Bottes Alpinestars RT-7 DRYSTAR",
              "Doublure: Membrane Drystar imperméable et respirante Doublure "
              "en lycra sur le dessus pour plus de confort")
    assert lu.impermeable is True
    assert lu.membrane == "drystar"


# =============================================================================
# 2. UN INTITULÉ N'EST PAS UNE AFFIRMATION, ET UNE ABSENCE S'ÉCRIT
# =============================================================================
#
# Motoblouz publie sur une partie de son catalogue une prose générée qui ANNONCE
# LES ABSENCES aussi explicitement que les présences, sous les mêmes intitulés
# de section. C'est le défaut du rayon blousons — « Imperméabilité et
# étanchéité — Absence de membrane » — retrouvé ici, en pire : le nom abstrait
# de la section ne dit rien, et la phrase qui suit dit NON.

def test_l_absence_de_gore_tex_n_annonce_pas_du_gore_tex():
    """LE cas d'école du rayon, et le plus cher :

        « Imperméabilité et étanchéité — Construction imperméable pour garder
          les pieds au sec en conditions humides — ABSENCE DE MEMBRANE
          GORE-TEX® INDIQUÉE, vérifiez les limitations d'étanchéité »

    La chaussure ressortait `membrane = 'gore-tex'` ET `gore_tex = True`. Le
    Gore-Tex est le nom qui justifie l'écart de prix du rayon, et il était posé
    sur la foi de la phrase qui dit qu'il n'y en a pas.

    L'imperméabilité, elle, RESTE : « Construction imperméable » est une
    affirmation du marchand, et elle n'est pas niée. Une garde qui l'aurait
    effacée aussi aurait corrigé la sur-affirmation par une sous-lecture.
    """
    t = ("Éléments réfléchissants pour améliorer la visibilité Imperméabilité "
         "et étanchéité Construction imperméable pour garder les pieds au sec "
         "en conditions humides Absence de membrane Gore-Tex® indiquée, "
         "vérifiez les limitations d'étanchéité selon l'usage")
    lu = lire("Baskets Moto X", t)
    assert lu.membrane is None
    assert lu.gore_tex is None
    assert lu.impermeable is True


def test_sans_membrane_etanche_n_est_pas_etanche():
    """FC-Moto, qui écrit court, le dit en six mots : « Version été AIR SANS
    MEMBRANE ÉTANCHE ». Les deux mots que l'extracteur cherchait — « membrane »
    et « étanche » — sont là, et la phrase dit l'inverse.

    Le second est le plus sournois : la négation est à quatorze signes de lui,
    derrière le mot qu'elle nie en premier.
    """
    t = ("*  Version été AIR sans membrane étanche *  Grandes surfaces en "
         "maille pour une ventilation maximale *  Léger et confortable à porter")
    lu = lire("Falco Grander Air Chaussures moto", t)
    assert lu.impermeable is None
    assert lu.membrane is None
    assert lu.ventilation is True     # celle-là, le texte l'affirme


def test_non_etanche_et_non_impermeable():
    """Trois formulations réelles, sur trois fiches différentes, et toutes les
    trois annonçaient une botte imperméable :

        « Les + […] NON ÉTANCHE ce qui signifie qu'il ne protège pas de la
          pluie et n'est pas prévu pour un usage sous forte averse »
        « PRODUIT NON IMPERMÉABLE, éviter l'exposition prolongée à la pluie
          pour préserver le cuir suédé »
        « Construction NON ÉTANCHE Idéal pour les conditions sèches »
    """
    for phrase in (
        "Les + Conçu pour homme Non étanche ce qui signifie qu'il ne protège "
        "pas de la pluie et n'est pas prévu pour un usage sous forte averse",
        "Produit non imperméable, éviter l'exposition prolongée à la pluie "
        "pour préserver le cuir suédé",
        "Intérieur en mesh respirant Construction non étanche Idéal pour les "
        "conditions sèches et estivales",
    ):
        assert lire("Baskets Moto X", phrase).impermeable is None, phrase


def test_pas_de_renfort_tibial():
    """La même prose générée, appliquée à une protection :

        « Renfort sélecteur intégré pour protéger la zone du levier de vitesse
          Renfort malléole présent pour maintien et protection latérale
          PAS DE RENFORT TIBIAL INTÉGRÉ et sliders non remplaçables »

    La botte ressortait avec ses trois protections, dont une que le marchand
    déclare absente. Les deux autres doivent rester : c'est la même phrase, et
    une garde qui les emporterait toutes serait aussi fausse que l'absence de
    garde.
    """
    t = ("Renfort sélecteur intégré pour protéger la zone du levier de vitesse "
         "Renfort malléole présent pour maintien et protection latérale "
         "Pas de renfort tibial intégré et sliders non remplaçables, "
         "information à prendre en compte pour l'usage et l'entretien")
    lu = lire("Bottes X", t)
    assert lu.protection_tibia is None
    assert lu.protection_selecteur is True
    assert lu.protection_malleole is True


def test_le_sans_qui_n_annonce_aucune_absence():
    """LE CONTRE-TEST, et c'est lui qui a dicté la largeur de la garde.

    Le rayon écrit « sans » quinze fois par fiche pour dire l'inverse d'une
    absence. Une garde large aurait effacé ces protections-là — et aurait fait
    BAISSER la couverture, ce qu'un total finit par trahir, mais après coup.

    Les quatre phrases sont réelles, et les quatre parlent de bottes qui ONT la
    chose qu'elles semblent nier.
    """
    cas = (
        ("temps de pluie sans infiltration Protection et renforts Protections "
         "malléoles intégrées pour limiter le risque de blessure",
         "protection_malleole"),
        ("une protection ciblée sans trop rigidifier la tige Renfort malléole "
         "et coussinets de cheville pour limiter les torsions",
         "protection_malleole"),
        ("porter les chaussures hors moto sans sacrifier l'intégration des "
         "protectionsProtection et renfortsInserts de malléole pour protéger "
         "la cheville en cas d'impact",
         "protection_malleole"),
        ("une meilleure circulation de l'air et une meilleure ventilation sans "
         "compromettre la protection contre les impacts",
         "ventilation"),
    )
    for phrase, champ in cas:
        assert getattr(lire("Bottes X", phrase), champ) is True, phrase


# =============================================================================
# 3. « PRÉDISPOSÉ » N'EST PAS « FOURNI » — ET LA RÉSERVE DOIT TOUCHER LE MOT
# =============================================================================

def test_le_protege_selecteur_en_option():
    """L'occurrence du rayon, écrite par Motoblouz sans espace avant la section
    suivante : « Patte arrière afin de faciliter l'enfilage Tige haute PROTÈGE
    SÉLECTEUR DXR EN OPTIONComposition: … ». La réserve est DERRIÈRE le mot,
    ce que le rayon casque n'avait jamais montré."""
    t = ("Patte arrière afin de faciliter l'enfilage Tige haute Protège "
         "sélecteur DXR en optionComposition: Matière extérieure :100% "
         "polyuréthaneMatière intérieure :100% polyester")
    lu = lire("Bottes DXR X", t)
    assert lu.protection_selecteur is None
    # La composition, elle, se lit : c'est le marchand qui nomme l'extérieur.
    assert lu.matiere == "synthétique"


def test_la_reserve_doit_toucher_le_mot_qu_elle_reserve():
    """Le défaut EN SENS INVERSE, et il ne se voyait pas davantage.

    Sur tout le rayon, la garde de préparation placée en amont d'une protection
    s'est déclenchée cinq fois, et les cinq étaient fausses. « adapté à » et
    « nécessite » sont des mots de préparation dans le rayon casque — « adapté
    pour recevoir un intercom » — et des phrases de vente ici :

        « Membrane imperméable et respirante ADAPTÉ À TOUTES LES CONDITIONS
          Protections: Protection de cheville en D3O »
        « une usure du slider NÉCESSITE LE REMPLACEMENT DE LA PAIRE
          Protection et renforts Renfort malléole présent »

    Les deux bottes perdaient leur protection de malléole sur la foi d'une
    phrase qui parlait d'autre chose.
    """
    t = ("Membrane imperméable et respirante adapté à toutes les "
         "conditionsProtections: Protection de cheville en D3OHomologuées CE")
    assert lire("Demi-bottes Sidi URBEX", t).protection_malleole is True

    t2 = ("Absence de sliders remplaçables impliquant qu'une usure du slider "
          "nécessite le remplacement de la paire Protection et renforts "
          "Renfort malléole présent pour maintien et protection latérale")
    assert lire("Baskets Moto X", t2).protection_malleole is True


def test_le_ce_d_une_protection_n_est_pas_le_ce_de_la_chaussure():
    """« Protections Seesoft™ HOMOLOGUÉE CE aux malléoles » ne dit pas que la
    chaussure est homologuée : le protecteur a sa propre certification. La
    même fiche le dit ailleurs, et c'est cette phrase-là qu'on garde."""
    t = ("Protège sélecteur en caoutchouc. Protections Seesoft™ homologuée CE "
         "aux malléoles. Renfort aux tibias. Homologation CE niveau 2.")
    assert lire("Bottes ARENA LADIES", t).homologation == "CE"
    # Seule, la certification de la pièce ne suffit pas.
    assert lire("Bottes X", "Protections malléoles D3O homologuées "
                            "CE.").homologation is None


# =============================================================================
# 4. LES LIMITES DE MOT, VÉRIFIÉES SUR LE FICHIER ET SUR SON COMPORTEMENT
# =============================================================================

def test_le_fichier_ne_contient_aucun_caractere_de_controle():
    """Le quatrième piège du rayon casque n'était pas une expression fausse,
    c'était une ÉCRITURE de fichier : les `\\b` des expressions régulières
    avaient été remplacés par des caractères de contrôle 0x08, invisibles à la
    lecture. C'est arrivé cinq fois sur ce projet.

    Ce fichier-ci en dépend plus qu'aucun autre : « PU », « TPU », « CE »,
    « D3O », « SRA » sont des abréviations de deux ou trois lettres, et sans
    limites de mot elles matchent n'importe quoi. On vérifie donc la source,
    pas seulement le comportement."""
    source = (Path(__file__).resolve().parents[1]
              / "src" / "mcpipe" / "caracteristiques" / "botte.py")
    texte = source.read_text(encoding="utf-8")
    assert [c for c in texte if ord(c) < 9] == []


def test_resemel_ne_doit_pas_se_lire_dans_microfibre_semelle():
    """LA LIMITE DE MOT QUI MANQUAIT VRAIMENT, et elle faisait BAISSER la
    couverture au lieu de la monter — c'est pour ça que personne ne l'avait vue.

    Le motif des pièces de rechange contenait `resemel` sans limite de mot.
    Motoblouz publie ses sections collées, sans espace :

        « …pour une durabilité supérieureSemelle avec motif de prise… »
        « …un rabat interne en microfibreSemelle externe amovible… »

    La fin de « microfib-RE » suivie de « SEMEL-le » forme « reSemel ».
    SOIXANTE-DIX-HUIT bottes réelles — des TECH 7, des TECH 10, des Sidi
    AGUEDA — étaient rendues VIDES, traitées comme des semelles de rechange.
    La fiche existait, elle n'avait simplement aucune caractéristique.
    """
    t = ("Matière: Tige en microfibre résistante à l'abrasion pour une "
         "durabilité supérieureSemelle externe amovible et changeable")
    lu = lire("Bottes cross Alpinestars TECH 10 2026", t)
    assert lu.renseignees() > 0
    assert lu.matiere == "synthétique"
    assert lu.categorie == "bottes"
    # …et la vraie pièce de rechange reste écartée.
    assert lire("FOX Instinct Semelle extérieure",
                "* Pièces de rechange officielles Fox Racing * Compatible avec "
                "les bottes Instinct").renseignees() == 0


def test_la_norme_citee_ne_fait_pas_d_une_botte_un_accessoire():
    """L'autre moitié du même dégât : le motif écartait tout texte contenant
    « pour bottes », alors que la phrase de norme du rayon est
    « certifié CE selon la norme EN 13634 POUR BOTTES MOTO ». Elle décrit la
    botte, pas une pièce vendue pour une botte.

    Douze fiches étaient concernées, dont dix bottes réelles. Les deux autres
    étaient de vrais accessoires — un séchoir — et ils devaient continuer à
    sortir : c'est pourquoi ils ont désormais leur propre mot.
    """
    t = ("Sécurité et normes Modèle certifié CE selon la norme EN 13634 pour "
         "bottes moto Conception conforme aux exigences européennes")
    assert lire("Demi-bottes Helstons LOGGER", t).homologation == "EN 13634"
    assert lire("Séchoir à bottes BikeTek noir",
                "Support pour bottes.").renseignees() == 0


def test_les_abreviations_courtes_ne_matchent_pas_n_importe_quoi():
    """Le symptôme qu'aurait donné une limite de mot perdue sur « PU », « TPU »
    ou « CE » : la leçon du « ABS » qui matchait « absorption »."""
    for phrase in (
        "Semelle offrant une excellente absorption des chocs et un grip fiable",
        "Chaussures épurées au design sobre pour un usage quotidien",
        "Coupe basse et coussinets de confort autour de la cheville",
    ):
        lu = lire("Bottes X", phrase)
        assert lu.matiere is None, phrase
        assert lu.homologation is None, phrase


# =============================================================================
# 5. LES DEUX AUTRES AXES, POUR QUE LES GARDES NE SOIENT PAS QUE DES REFUS
# =============================================================================

def test_la_categorie_se_lit_dans_le_titre():
    """« Demi-bottes » contient « bottes », et l'ordre de la liste est ce qui
    les départage. Les chaussettes sont une valeur du marchand, et rien de plus
    ne se lit dedans."""
    assert lire("Bottes cross Falco LEVEL 2 2023", "").categorie == "bottes"
    assert lire("Demi-bottes Sidi URBEX WATERPROOF", "").categorie == "demi-bottes"
    assert lire("Baskets Moto Alpinestars SP-2", "").categorie == "baskets moto"
    chaussettes = lire("Lenz Merino Compression Chaussettes",
                       "* Conception extra mince * pas de rembourrage")
    assert chaussettes.categorie == "chaussettes"
    assert chaussettes.renseignees() == 1


def test_l_univers_ambigu_ne_se_lit_qu_en_tete_de_titre():
    """« Baskets Alpinestars META TRAIL » est un nom de modèle, pas un usage :
    la chaussure est une basket urbaine, et l'annoncer « trail » enverrait
    l'acheteur aventure sur un modèle sans membrane."""
    assert lire("Baskets Alpinestars META TRAIL", "").univers is None
    assert lire("Bottes trail Gaerne G-ADVENTURE", "").univers == "trail"
    assert lire("Bottes cross Alpinestars TECH 7 2025", "").univers == "cross"
    # Dans la prose, il faut une ancre d'usage explicite.
    assert lire("Bottes X", "Coupe sportive et look affirmé").univers is None
    assert lire("Bottes X", "conçues pour une utilisation Café racer, Custom "
                            "et Cruiser").univers == "custom"


# =============================================================================
# 6. LA RÈGLE QUI PRIME SUR TOUTES LES AUTRES
# =============================================================================

def test_le_doute_rend_rien():
    """Un `None` n'écrit aucune ligne en base ; une caractéristique fausse
    coûte la confiance. On ne devine jamais à partir du prix, de la marque ni
    de la catégorie."""
    vide = lire("", "")
    assert vide.renseignees() == 0
    muet = lire("Bottes Kenny Performance orange- 47", "Bottes confortables et "
                                                       "résistantes.")
    assert muet.matiere is None
    assert muet.homologation is None
    assert muet.impermeable is None
    assert muet.protection_malleole is None


# =============================================================================
# 7. LA FUSION
# =============================================================================

def test_fusion_le_premier_qui_sait_repond():
    """L'appelant passe les marchands du plus disert au plus avare."""
    disert = lire("Bottes X", "Matière: Tige en cuir de vachette Protections: "
                              "Renfort malléole")
    avare = lire("Bottes X", "* Semelle antidérapante Vibram")
    out = fusionner([disert, avare])
    assert out.matiere == "cuir"
    assert out.protection_malleole is True
    assert out.semelle_antiderapante is True


def test_fusion_ce_ne_contredit_pas_en_13634():
    """Un marchand qui écrit « EN 13634 » et un autre qui écrit « CE » ne se
    contredisent pas : le second est moins précis, pas faux. On garde la valeur
    la plus précise, quel que soit l'ordre d'appel."""
    precis = lire("Bottes X", "* Chaussures de protection pour motocyclistes, "
                              "EN 13634:2017")
    vague = lire("Bottes X", "Bottes moto homologuées CE idéales sur route")
    assert fusionner([precis, vague]).homologation == "EN 13634"
    assert fusionner([vague, precis]).homologation == "EN 13634"


def test_fusion_un_desaccord_d_indice_ne_vaut_pas_mieux_qu_un_silence():
    """Deux sources qui se disputent une donnée de sécurité ne valent pas mieux
    qu'aucune source."""
    a = Botte(indice_abrasion=1, indice_coupure=2)
    b = Botte(indice_abrasion=2, indice_coupure=2)
    out = fusionner([a, b])
    assert out.indice_abrasion is None
    assert out.indice_coupure == 2
    assert fusionner([]).renseignees() == 0
