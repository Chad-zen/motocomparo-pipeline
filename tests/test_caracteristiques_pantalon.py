"""Les pièges du rayon pantalons, trouvés en relisant l'échantillon.

Le module `pantalon.py` avait été écrit sans qu'aucune de ses extractions ait
été relue. Ce fichier est le résultat de la relecture : catégorie 7, 8 211
fiches, 11 249 descriptions marchandes, passées à `lire()` puis rouvertes une à
une avec LA PHRASE AUTOUR de chaque détection.

Chaque test est bâti sur une phrase RÉELLE, copiée d'une description de
l'échantillon. Aucune n'a été inventée : une phrase inventée teste ce qu'on a
imaginé, pas ce que les marchands écrivent.

Et la leçon des trois rayons précédents s'est vérifiée une quatrième fois :
AUCUN de ces défauts ne se voyait dans un total, et tous sauf deux FAISAIENT
MONTER la couverture. Les corrections l'ont fait baisser, et c'est ce qu'on
attendait d'elles :

    coques_hanches   2 467 -> 2 349   dont 'fourni' 1 698 -> 1 576
    membrane         1 287 -> 1 284
    ventilation      1 814 -> 1 796
    coques_genoux    3 137 -> 3 137   (53 lectures changent de valeur
                                       sans changer le total : 27 rendues au
                                       carton, 26 rendues à la poche vide)

Ce dernier chiffre est le plus instructif du lot : un total parfaitement
immobile au-dessus de cinquante-trois erreurs corrigées.
"""

from __future__ import annotations

from pathlib import Path

from mcpipe.caracteristiques.pantalon import Pantalon, fusionner, lire


# =============================================================================
# 1. UNE POCHE EST VIDE — c'est sa définition, et c'était LE défaut du rayon
# =============================================================================

def test_une_poche_a_cles_n_est_pas_une_coque_de_hanche():
    """Le pire de tous, parce qu'il ne parle même pas de protection.

    L'ancre des hanches accepte « poche ... hanche », et le silence autour
    d'elle valait « fourni ». Résultat : une poche à clés et des poches cargo
    annoncées comme des coques de hanches livrées avec le pantalon.

    306 lectures de hanches sur 2 467 avaient une POCHE pour ancre. On rend
    `None` quand la poche ne nomme aucune protection : le texte parle de
    rangement, pas de sécurité, et il n'y a rien à en tirer.
    """
    for phrase in (
        "Fermeture micrométrique avec bouton pressionAjustement de la taille "
        "par 2 bandes VelcroPoche intérieure à la zone des hanches pour y "
        "ranger des clés",
        "Deux poches cargo, deux poches hanches et une poche arrière",
        "* sangles réglables sur les jambes inférieures * sangles réglables "
        "à la taille * poches aux hanches",
    ):
        assert lire("", phrase).coques_hanches is None, phrase


def test_une_poche_qui_nomme_une_protection_reste_une_poche_vide():
    """Et là le texte parle bien de coques — mais il parle de leur EMPLACEMENT.

    Les quatre phrases ci-dessous ressortaient « fournies ». Aucune ne dit que
    la coque est dans le carton ; toutes disent qu'il y a de la place pour elle.
    Le défaut de fond était le défaut par défaut : sans marqueur, l'extracteur
    remplissait. Une poche se vide par défaut, elle ne se remplit pas.
    """
    for phrase in (
        "Certification EN 1621-1 EN 17092-4 APoches réglables pour les "
        "protections genoux amovibles ALPHA EN1621-1Poches pouvant accueillir "
        "des protections hanches",
        "Une poche supplémentaire pour armure de hanche homologuée CE",
        "Poches de protecteur sur les hanches",
        "Protection et renforts Poches prévues aux genoux et aux hanches pour "
        "accueillir des protections amovibles",
    ):
        assert lire("", phrase).coques_hanches == "prepare", phrase


def test_la_poche_se_decrit_avec_un_adjectif_au_milieu():
    """La garde exigeait « poche pour » ou « poche prévue pour », collées.

    « Poches RÉGLABLES pour les protections genoux amovibles ALPHA EN1621-1 »
    et « Poche RÉGLABLE pour protection genou » ne passaient ni l'une ni
    l'autre : un adjectif entre le nom et la préposition suffisait à faire
    d'une poche vide une genouillère fournie. Les deux phrases sont dans la
    fiche produit du même jean, l'une pour les genoux, l'autre pour les hanches.
    """
    t = ("Doublure fixeProtections: Certification EN 1621-1 EN 17092-4 A"
         "Poches réglables pour les protections genoux amovibles ALPHA "
         "EN1621-1Poches pouvant accueillir des protections hanches")
    assert lire("", t).coques_genoux == "prepare"

    t2 = ("Protections: Protections genoux CE amovibles OMEGA EN1621-1 Niveau 1"
          "Poche réglable pour protections genouxPoche pour les protections "
          "hanches")
    assert lire("", t2).coques_genoux == "prepare"


def test_une_coque_citee_sans_reserve_reste_fournie():
    """L'inverse doit rester vrai, sinon la garde ne sert qu'à tout refuser.

    1 464 fenêtres de hanches sur 2 467 ne portent NI marqueur de préparation
    NI marqueur de fourniture. Vingt-deux d'entre elles ont été relues au
    hasard : les vingt-deux décrivaient une coque livrée avec le pantalon. Le
    défaut par défaut « fourni » est donc juste — tant que l'ancre n'est pas
    une poche.
    """
    for phrase in (
        "Protections genoux homologuées CE niveau 1 Protections hanches "
        "homologuées CE niveau 1",
        "Coques de protections hanches et genoux homologuées CE niveau 1",
        "Protections hanches certifiées CE niveau 2 amovibles",
    ):
        assert lire("", phrase).coques_hanches == "fourni", phrase


def test_le_marqueur_le_plus_proche_de_l_ancre_gagne_toujours():
    """Non-régression sur la garde que le fichier documentait déjà.

    « (en option) » est à trente-trois signes de l'ancre des genoux, « inclut »
    à onze. Les genouillères sont dans le carton, les coques de hanches non.
    """
    t = ("Protections de hanches SEESMART RV33 CE-niveau 1 (en option) et "
         "inclut des protections de genoux SEESMART CE-niveau 1 RV36")
    p = lire("", t)
    assert p.coques_genoux == "fourni"
    assert p.coques_hanches == "prepare"


# =============================================================================
# 2. UNE NÉGATION QUI ARRIVE APRÈS — la borne qui tombe trop tard
# =============================================================================

def test_la_poche_du_coccyx_ne_vide_pas_celle_des_hanches():
    """Le coccyx est optionnel, les hanches ne le sont pas, et tout est collé.

    « Protections CE aux hanchesPoche pour protection du coccyx optionnelle »
    — Motoblouz aplatit son HTML sans le moindre séparateur. La borne de
    fenêtre était posée sur le seul mot « coccyx », ce qui laissait « Poche
    pour protection du » DANS la fenêtre des hanches : les coques de hanches
    ressortaient « prepare » sur la réserve écrite pour une autre pièce.

    La borne prend maintenant toute la phrase du coccyx, son verbe de
    préparation compris.
    """
    t = ("Protections :Protections de genoux SAS TEC ajustables certifiées CE "
         "EN 1621-1:2012 Protections CE aux hanchesPoche pour protection du "
         "coccyx optionnelle (article 9315)")
    p = lire("", t)
    assert p.coques_hanches == "fourni"
    assert p.coques_genoux == "fourni"


def test_la_predisposition_du_coccyx_ne_vide_pas_celle_des_hanches():
    """Même défaut, autre tournure : ici le verbe précède le nom de la pièce.

    « Protections aux hanches, certifiées CE EN 1621-1:2012Prédisposé à
    recevoir la protection coccyx ». Ancrée sur « coccyx », la borne laissait
    « Prédisposé à recevoir la » dans la fenêtre des hanches.
    """
    t = ("Protections aux hanches, certifiées CE EN 1621-1:2012Prédisposé à "
         "recevoir la protection coccyx")
    assert lire("", t).coques_hanches == "fourni"


def test_adapte_a_la_route_n_est_pas_adapte_a_recevoir():
    """Un mot de la garde du rayon casque qui ne se transpose pas tel quel.

    `casque.py` accepte « adapté à » comme marqueur de préparation, et il a
    raison : sur un casque, ce qui suit est toujours une pièce. Sur un
    pantalon, ce qui suit est un usage.

        « ...un niveau de protection global ADAPTÉ À LA ROUTE Protections CE
          niveau 2 aux genoux et aux hanches (EN 1621-1:2012) »
        « Certification CE classe AA qui assure un niveau de protection ADAPTÉ
          À LA PRATIQUE de la moto sur route Protections genoux Nucleon Flex
          Plus CE niveau 1 »

    Les deux annonçaient les coques en option. Elles sont fournies. 17 fenêtres
    de hanches et 28 de genoux étaient dans ce cas — et le défaut faisait
    BAISSER le nombre de coques fournies, ce qui le rendait rassurant.
    """
    for phrase in (
        "Protection et renforts Certifié EN17092 AAA pour attester d'un niveau "
        "de protection global adapté à la route Protections CE niveau 2 aux "
        "genoux et aux hanches (EN 1621-1:2012) pour une absorption d'énergie "
        "renforcée en cas d'impact",
        "Certification CE classe AA qui assure un niveau de protection adapté "
        "à la pratique de la moto sur routeProtections genoux Nucleon Flex "
        "Plus CE niveau 1 qui absorbent efficacement les impacts",
    ):
        p = lire("", phrase)
        assert p.coques_genoux == "fourni", phrase

    # Et « adapté à » garde son sens de préparation quand ce qui suit est
    # bien une pièce à recevoir.
    t = ("Pantalon adapté pour recevoir des protections de hanches vendues "
         "séparément")
    assert lire("", t).coques_hanches == "prepare"


# =============================================================================
# 3. UN INTITULÉ N'EST PAS UNE AFFIRMATION, ET LA NÉGATION EST DANS LA PHRASE
# =============================================================================

def test_sans_membrane_gore_tex_n_est_pas_un_gore_tex():
    """Le défaut des blousons, mot pour mot, et sur la marque qui fait le prix.

        « Adapté aux usages urbain et roadster pour des trajets quotidiens et
          balades routières NON IMPERMÉABLE ET SANS MEMBRANE GORE-TEX®,
          prévoir une protection pluie séparée pour roulages sous la pluie »

    Le mot « membrane » est là, le mot « Gore-Tex » est là, et le pantalon n'a
    ni l'un ni l'autre. Trois fiches sortaient « gore-tex » sur la foi de la
    phrase qui dit qu'elles ne le sont pas.

    Le coupable n'était pas la fenêtre mais le REPLI : `_membrane()` cherchait
    « gore-tex » dans tout le texte sans jamais regarder ce qu'on en disait.
    """
    t = ("Pantalon Moto GMS TAMPA CARGO: Adapté aux usages urbain et roadster "
         "pour des trajets quotidiens et balades routières Non imperméable et "
         "sans membrane Gore-Tex®, prévoir une protection pluie séparée pour "
         "roulages sous la pluie")
    assert lire("", t).membrane is None


def test_la_membrane_reelle_se_lit_toujours():
    """L'inverse doit rester vrai. Trois écritures réelles du rayon, et la
    distinction « laminé » que la facette du marchand expose.

    Une membrane maison n'est pas un Gore-Tex : c'est le même piège de genre et
    de sous-genre que « thermoplastique » n'est pas « polycarbonate » sur le
    rayon casque.
    """
    assert lire("", "Imperméabilité et étanchéité Membrane Gore-Tex® laminée "
                    "2C/3C intégrée pour garder le pilote au sec sans ajouter "
                    "de volume externe.").membrane == "gore-tex lamine"
    assert lire("", "Imperméabilité et étanchéité Membrane GORE-TEX® qui assure "
                    "une protection efficace contre la pluie").membrane == "gore-tex"
    assert lire("", "Membrane solto-TEX® laminée offrant une barrière "
                    "imperméable intégrée").membrane == "membrane"


def test_une_membrane_coupe_vent_n_est_pas_une_membrane_impermeable():
    """Non-régression sur la garde que le fichier documentait déjà : on exige
    l'imperméabilité EXPLICITE dans la même fenêtre que la membrane."""
    t = ("La doublure softshell en micropolaire chaude avec membrane coupe-vent "
         "et traitement d'évacuation de l'humidité")
    assert lire("", t).membrane is None


def test_la_ventilation_qu_on_bouche_n_est_pas_une_ventilation():
    """La négation arrive AVANT le mot, et il faut lire TOUTES les occurrences.

        « Une fermeture éclair de connexion permet de relier le pantalon à une
          veste compatible pour LIMITER LES ENTRÉES D'AIR et protéger le bas
          du dos »
        « Boucles de ceinture compatibles avec connexion blouson pour limiter
          les entrées d'air en position de conduite »

    « entrées d'air » y désigne ce que le vêtement EMPÊCHE. Dix-huit fiches
    annonçaient une ventilation sur la phrase qui dit qu'on la bouche, et les
    dix-huit étaient des pantalons de ville sans la moindre aération.
    """
    for phrase in (
        "Une fermeture éclair de connexion permet de relier le pantalon à une "
        "veste compatible pour limiter les entrées d'air et protéger le bas "
        "du dos",
        "Boucles de ceinture compatibles avec connexion blouson pour limiter "
        "les entrées d'air en position de conduite",
    ):
        assert lire("", phrase).ventilation is None, phrase


def test_une_seule_aeration_non_niee_suffit():
    """Le corollaire, et c'est lui qui impose de balayer toutes les occurrences.

    Une garde qui s'arrête à la PREMIÈRE occurrence rate l'aération réelle
    quand le texte commence par la phrase du zip de raccordement. Les deux
    tournures cohabitent dans les fiches Motoblouz générées.
    """
    t = ("Zip de connexion pour limiter les entrées d'air Ventilation et "
         "respirabilité Zips d'aération sur les cuisses pour ajuster le flux "
         "d'air en roulage")
    assert lire("", t).ventilation is True


# =============================================================================
# 4. LES PIÈGES DÉJÀ TENUS PAR LE FICHIER — non-régression
# =============================================================================

def test_une_piece_n_est_pas_l_autre():
    """La doublure ne dit rien du tissu extérieur, et le cuir fait le prix.

    « Les panneaux internes en cuir de chèvre au niveau des genoux » et
    « Bouclier thermique en cuir extra long » sont deux pantalons TEXTILE. Le
    cuir n'est lu que s'il est la matière ANNONCÉE — titre, ou tête de section.
    """
    t = ("Pantalon Moto Alpinestars AMT-8: Matière: Textile technique souple, "
         "léger et résistant à l'abrasionLes panneaux internes en cuir de "
         "chèvre au niveau des genoux offrent une sensation de contact maximale")
    assert lire("Pantalon Moto Alpinestars AMT-8 STRETCH DRYSTAR XF PANTS",
                t).matiere != "cuir"

    assert lire("Pantalon cuir DRACK FURYGAN",
                "Pantalon moto en cuir typé racing. Construction en cuir de "
                "vachette.").matiere == "cuir"


def test_type_b_est_un_protecteur_pas_une_classe_de_vetement():
    """EN 1621-1 classe les COQUES en type A / type B ; EN 17092 classe le
    VÊTEMENT en AAA/AA/A/B/C. Les deux se côtoient dans la même phrase.

    « Protections IX-PROSOFT niveau 1 type A aux genouxProtections hanches
    Heptagon niveau 1 type B » ferait de ce pantalon un vêtement de classe B —
    la classe sans résistance à l'abrasion. C'est l'inverse de ce que dit la
    phrase.
    """
    t = ("Protections IX-PROSOFT niveau 1 type A aux genouxProtections hanches "
         "Heptagon niveau 1 type B")
    assert lire("", t).homologation is None


def test_classic_n_est_pas_la_classe_C():
    """« Classic » est un des noms de modèle les plus courants du rayon, et la
    classe C est celle qui fait fuir un acheteur."""
    for titre in (
        "Pantalon cross O'Neal ELEMENT - CLASSIC - BLACK",
        "Jean Moto Richa CLASSIC",
        "Pantalon Hebo TECH MONTESA CLASSIC",
    ):
        assert lire(titre, "").homologation is None, titre


def test_racing_est_un_nom_de_marque_sur_ce_rayon():
    """Fly Racing, Moose Racing et Thor Racing font des pantalons de CROSS.
    Lire « racing » comme « sport » enverrait le rayon tout-terrain entier dans
    l'univers piste."""
    assert lire("Pantalon cross enfant Fly Racing Kinetic K220", "").univers == "cross"
    assert lire("Pantalon tout-terrain Moose Racing Sahara", "").univers == "cross"


def test_le_niveau_se_lit_vers_l_avant_jamais_vers_l_arriere():
    """« Protections de genoux [...] niveau 2 [...] Protections de hanches
    [...] niveau 1 » : une fenêtre symétrique autour de « hanches » remonte
    jusqu'au niveau des genoux."""
    t = ("Protections de genoux impacTec® certifiées selon la norme "
         "EN 1621-1:2012 niveau 2 pour une protection localisée Protections de "
         "hanches impacTec® certifiées selon la norme EN 1621-1:2012 niveau 1 "
         "pour une protection complémentaire")
    p = lire("", t)
    assert p.niveau_genoux == 2
    assert p.niveau_hanches == 1


# =============================================================================
# 5. LA FUSION : deux sources qui se contredisent ne valent pas mieux qu'une
# =============================================================================

def test_fusion_un_desaccord_sur_les_coques_ne_promet_rien():
    """Promettre une pièce que l'acheteur devra payer est la faute la plus
    chère du rayon. Un marchand qui vend « avec coques hanches » et un autre
    qui vend « prédisposé » ne décrivent pas le même carton."""
    a = Pantalon(coques_hanches="fourni")
    b = Pantalon(coques_hanches="prepare")
    assert fusionner([a, b]).coques_hanches is None
    assert fusionner([b, a]).coques_hanches is None
    assert fusionner([a, Pantalon()]).coques_hanches == "fourni"


def test_fusion_un_desaccord_d_homologation_ne_vaut_pas_mieux_qu_un_silence():
    """Annoncer AAA sur un vêtement de classe A est une information de sécurité
    fausse, et deux sources opposées ne tranchent rien."""
    assert fusionner([Pantalon(homologation="AAA"),
                      Pantalon(homologation="A")]).homologation is None
    assert fusionner([Pantalon(homologation="AA"),
                      Pantalon()]).homologation == "AA"


def test_fusion_de_rien_ne_donne_rien():
    assert fusionner([]).renseignees() == 0
    assert fusionner([Pantalon(), Pantalon()]).renseignees() == 0


def test_un_texte_vide_ne_renseigne_rien():
    """Speedway écrit soixante-quinze signes de médiane, et parfois zéro."""
    assert lire("", "").renseignees() == 0
    assert lire(None, None).renseignees() == 0


# =============================================================================
# 6. LES LIMITES DE MOT, VÉRIFIÉES SUR LE FICHIER LUI-MÊME
# =============================================================================

def test_le_fichier_ne_contient_aucun_caractere_de_controle():
    """Le quatrième piège du rayon casque n'était pas une expression fausse,
    c'était une ÉCRITURE de fichier : les `\\b` des expressions régulières
    avaient été remplacés par des caractères de contrôle 0x08, invisibles à la
    lecture. C'est arrivé cinq fois sur ce projet.

    Ce fichier-ci dépend de ses `\\b` autant que les autres : sans eux, `A`
    matcherait n'importe quel mot et la classe EN 17092 deviendrait du bruit,
    `MX` matcherait au milieu d'une référence, et `dos` matcherait « dossier ».
    On vérifie donc la source, pas seulement le comportement."""
    source = (Path(__file__).resolve().parents[1]
              / "src" / "mcpipe" / "caracteristiques" / "pantalon.py")
    texte = source.read_text(encoding="utf-8")
    assert [c for c in texte if ord(c) < 9] == []


def test_la_classe_A_ne_matche_pas_n_importe_quel_mot():
    """Le symptôme qu'aurait donné une limite de mot perdue."""
    for phrase in (
        "Coupe Regular Fit, poches Cargo, ceinture Ajustable",
        "Certifiée CE amovible aux genoux, excellente absorption des chocs",
        "Pantalon de classe Affaires pour les longs trajets",
    ):
        assert lire("", phrase).homologation is None, phrase
