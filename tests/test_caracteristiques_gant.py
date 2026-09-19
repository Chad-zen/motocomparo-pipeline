"""Les pièges du rayon gants, trouvés en relisant l'échantillon.

Chaque phrase de ce fichier est une VRAIE phrase de marchand, copiée depuis
l'échantillon du rayon (catégorie 8, 9 895 fiches). Aucune n'a été inventée
pour faire passer un test : elles ont toutes fait échouer l'extracteur avant
de le faire réussir.

Comme pour le rayon casque, AUCUN de ces défauts n'était visible dans un taux
de couverture, et la plupart le FAISAIENT MONTER — ils ressemblaient à une
bonne nouvelle. Les deux exceptions sont instructives : une garde de négation
trop large et une limite de mot mal écrite faisaient BAISSER la couverture,
et c'est le seul type d'erreur qu'un total finit par trahir.

Un extracteur se juge en lisant ses sorties, pas en regardant son taux de
remplissage.
"""

from __future__ import annotations

from mcpipe.caracteristiques.gant import Gant, fusionner, lire


# =============================================================================
# LE PIÈGE DU RAYON : une pièce n'est pas l'autre, et un gant en a six
# =============================================================================

def test_le_renfort_de_paume_n_est_pas_la_paume():
    """LE piège du rayon, en une phrase : les deux affirmations se suivent.

    « Renfort de paume EN CUIR » puis « Paume EN DAIM SYNTHÉTIQUE ». Le renfort
    est en cuir, la paume ne l'est pas. Lue sans garde, la paume ressortait
    « cuir » — la matière qui fait le prix d'un gant, sur la pièce qui l'use.
    """
    t = ("Tissu en maille respirant Renfort de paume en cuir "
         "Paume en daim synthétique Protection ergonomique des articulations en TPU")
    assert lire("", t).matiere_paume == "cuir synthétique"


def test_la_matiere_du_gant_ne_se_deduit_pas_d_une_piece():
    """La facette « Matière » du marchand vaut pour le GANT ENTIER.

    « Les "+": Gants confortables avec PAUME EN CUIR avec coque de protection »
    est une phrase sur la paume, et rien n'y sépare « Gants » de « en cuir » :
    ni deux-points ni astérisque. Le gant en question a le dos en softshell.
    L'annoncer « cuir » aurait rempli la facette la plus demandée avec une
    demi-vérité.
    """
    t = ("Dos de la main en softshell Paume de la main en cuir de chèvre "
         "Les \"+\": Gants confortables avec paume en cuir avec coque de protection")
    assert lire("", t).matiere is None


def test_la_matiere_du_gant_se_lit_quand_le_texte_parle_du_gant():
    """L'inverse doit rester vrai, sinon la garde ne sert qu'à tout refuser."""
    assert lire("Gants cuir/textile Bering Kiff noir", "").matiere == "cuir et textile"
    assert lire("", "Les Forest sont des gants entièrement en cuir de chèvre "
                    "au design sobre.").matiere == "cuir"
    assert lire("", "Gants d'été Old school en textile mesh et cuir, compatible "
                    "aux écrans tactille.").matiere == "cuir et textile"
    assert lire("Gant de moto en maille pour femmes", "").matiere == "textile"


def test_le_slider_d_avant_bras_n_est_pas_un_slider_de_paume():
    """Un gant porte jusqu'à trois sliders, et ils ne protègent pas la même
    chose. « Protection de l'avant-bras grâce au Cuff Slider en TPR » et
    « Slider sur le dessus de la main » ne disent rien de la paume — qui est
    justement la seule surface qui touche le bitume dans une chute."""
    assert lire("", "Protection de l'avant-bras grâce au Cuff Slider en TPR "
                    "Double-système de fermeture par patte velcro").slider_paume is None
    assert lire("", "Renfort en cuir digital coté paume Slider sur le dessus "
                    "de la main").slider_paume is None
    assert lire("", "Coque d'articulations souple invisible, renfort de paume "
                    "Slider en TPR.").slider_paume is True


def test_la_coque_de_torse_n_est_pas_une_coque_d_articulations():
    """Un flux traduit automatiquement a laissé de la prose de blouson dans des
    fiches de gants : « Dispositifs de protection et de renfort : coque de
    torse ADV, renfort en cuir pour les doigts sur la paume ». Un gant ne
    protège pas la poitrine, et l'écrire aurait été grotesque autant que faux.
    """
    t = ("Caractéristiques de protection et de renforcement : Coque du torse "
         "Manchette : longue Fermeture : double fermeture au poignet")
    assert lire("", t).coque_articulations is None


# =============================================================================
# LE GENRE ET SON SOUS-GENRE
# =============================================================================

def test_l_aspect_carbone_n_est_pas_du_carbone():
    """« Coque de protection ASPECT CARBONE au niveau des phalanges » est une
    finition imprimée. Le carbone est ce qui justifie cent euros d'écart sur un
    gant racing ; l'annoncer sur un gant qui en imite la texture est la même
    sur-affirmation que « polycarbonate » sur un casque en thermoplastique."""
    t = ("Gants racing en cuir. Homologation CE. Coque de protection aspect "
         "carbone au niveau des phalanges. Slider au niveau de la paume.")
    lu = lire("", t)
    assert lu.coque_articulations is True
    assert lu.matiere_coque is None


def test_la_coque_sans_matiere_reste_sans_matiere():
    """« Coque de Protection » tout court est un genre, pas une matière. On
    rend la présence, et `None` pour le reste."""
    lu = lire("", "Protections: Coque de ProtectionRenfort PaumeLes \"+\": Grip")
    assert lu.coque_articulations is True
    assert lu.matiere_coque is None
    assert lire("", "Protection du poing par une coque en carbone. Paume "
                    "renforcée par des fibres aramides.").matiere_coque == "carbone"


def test_le_cuir_synthetique_n_est_pas_du_cuir():
    """Le sous-genre CONTREDIT le genre ici, au lieu de le préciser : un gant
    en synthétique annoncé « cuir » vaut cent euros de moins que sa fiche.

    Et les deux motifs matchent à la MÊME position — « cuir » est le début de
    « cuir synthétique ». Un tri qui départageait par ordre alphabétique
    faisait gagner « cuir ». Cent quatre-vingt-trois gants étaient concernés,
    et la couverture n'avait pas bougé d'une ligne.
    """
    assert lire("", "Paume en cuir synthétique AX Suede embossé pour un grip "
                    "optimal").matiere_paume == "cuir synthétique"
    assert lire("", "Paume en cuir de chèvre pleine fleur "
                    "souple").matiere_paume == "cuir"


def test_ce_n_est_pas_en_13594():
    """« Homologués CE » est une affirmation générique ; « EN 13594:2015 » nomme
    la norme. Promouvoir l'un en l'autre prêterait au gant une norme que le
    texte ne cite pas. On rend donc la valeur générique : moins précise, vraie.
    """
    assert lire("", "Serrage poignet par patte / velcro. Homologués "
                    "CE.").homologation == "CE"
    assert lire("", "Homologués selon la norme EN 13594:2015 niveau 1 "
                    "KP.").homologation == "EN 13594"
    assert lire("", "Gants de protection pour motards : EN 13594-2015 Niveau "
                    "1").homologation == "EN 13594"
    # « FR 13594 » : la traduction automatique d'un flux a pris « EN » pour le
    # nom d'une langue et l'a traduit.
    assert lire("", "* FR 13594:2015 * Indice tactile "
                    "intelligent").homologation == "EN 13594"


# =============================================================================
# LES NIVEAUX QUI N'EN SONT PAS
# =============================================================================

def test_le_niveau_d_une_coque_n_est_pas_le_niveau_du_gant():
    """« Protections phalanges en Carbone homologuées CE NIVEAU 2 ».

    La coque de phalanges est certifiée séparément, sous une autre norme, avec
    ses propres niveaux. Annoncer ce gant « niveau 2 » — le niveau des gants
    racing — sur la foi d'une coque est exactement l'erreur que la couverture
    compte comme un succès.
    """
    t = ("Protections: Protections phalanges en Carbone homologuées CE niveau 2 "
         "Pads de protections des articulations Renfort scaphoïde")
    assert lire("", t).niveau is None


def test_le_nom_du_modele_n_est_pas_un_niveau():
    """« Richa LEVEL 2 in 1 Gore-Tex gants de moto imperméables » est un nom de
    modèle, et « Technologie Gore 2 en 1 » une technologie de membrane. Aucun
    des deux ne parle de résistance à l'abrasion."""
    t = ("Level 2 in 1 Gore-Tex gants de moto imperméables * membrane Gore-Tex "
         "respirante, coupe-vent et imperméable * Technologie Gore 2 en 1")
    assert lire("", t).niveau is None


def test_le_niveau_de_chauffe_n_est_pas_un_niveau_de_protection():
    """Un gant chauffant a trois ou quatre niveaux, et ce sont des watts.

    « Système chauffant: Niveau 1 : bleu / 32° / 8h d'autonomie Niveau 2 : vert
    / 40°C / 4h d'autonomie », et un « Homologués CE » en fin de fiche suffisait
    à adosser « Niveau 2 » à une norme. Le gant ressortait au niveau des gants
    racing sur la foi d'un réglage de résistance.
    """
    t = ("Doublure thermique Primaloft Système chauffant: Niveau 1 : bleu / 32 / "
         "8h d'autonomie Niveau 2 : vert / 40C / 4h d'autonomie Homologués CE")
    lu = lire("Gants chauffants SHIRO", t)
    assert lu.niveau is None
    assert lu.chauffant is True


def test_le_niveau_reel_est_bien_lu():
    """Sinon la garde ne sert qu'à tout refuser. Les six écritures du rayon."""
    for phrase, attendu in (
        ("Certifié EN 13594:2015 niveau 1KP garantissant une protection", "1"),
        ("Homologués CE EN13594 niveau 1KP", "1"),
        ("Homologués CE, niveau 1 KP, et conformes à la norme EN 13594:2015", "1"),
        ("Schutzhandschuhe für Motorradfahrer Level 1 KP (EN 13594:2015)", "1"),
        ("Les gants Kenny SF-Tech suivent les normes EPI 1KP", "1"),
        ("* Gants de protection pour motards (EN 13594 Niveau 2)", "2"),
    ):
        assert lire("", phrase).niveau == attendu, phrase


def test_kp_ne_se_cherche_pas_sans_sa_casse():
    """« KP » est cherché sans `re.I`, et « CE » aussi — parce qu'en minuscules
    « ce » est un des mots les plus fréquents du français. Une recherche
    insensible à la casse aurait homologué le rayon entier."""
    assert lire("", "Homologués CE niveau 1 KP.").kp is True
    assert lire("", "Ce gant est confortable, ce qui compte.").homologation is None
    assert lire("", "Ce gant est confortable, ce qui compte.").kp is None


# =============================================================================
# CE QUE LE TEXTE NIE, ET CE QU'IL NE NIE PAS
# =============================================================================

def test_sans_coque_veut_dire_sans_coque():
    """Les descriptions longues DISENT ce qui manque, et c'est un service rendu
    à l'acheteur qu'il ne faut pas retourner contre lui. Deux marchands
    indépendants décrivent le même gant :

        « Conçus SANS coque de phalanges afin de privilégier confort et liberté »
        « PAS DE coque phalanges pour plus de confort. »

    Lues comme des présences, elles transformaient un gant dépourvu de
    protection en gant protégé. C'est le faux positif le plus grave du fichier.
    """
    for phrase in (
        "PWR Shield sur la paume pour renforcer la résistance à l'abrasion "
        "Conçus sans coque de phalanges afin de privilégier confort et liberté",
        "PWR Shield sur la paume renforce la résistance à l'abrasion. "
        "Pas de coque phalanges pour plus de confort.",
    ):
        assert lire("", phrase).coque_articulations is False, phrase


def test_absence_de_protection_scaphoide():
    """Le scaphoïde est l'os du poignet qui casse en premier, et le seul endroit
    du rayon où un marchand écrit noir sur blanc que la protection manque :
    « ABSENCE DE protection scaphoïde, à prendre en compte si vous recherchez
    une protection complète du poignet »."""
    t = ("Niveau de certification 1KP indiqué pour comparer les modèles "
         "Absence de protection scaphoïde, à prendre en compte si vous "
         "recherchez une protection complète du poignet")
    assert lire("", t).protection_scaphoide is False
    assert lire("", "Renfort scaphoïde Pont de doigt entre l'auriculaire et "
                    "l'annulaire").protection_scaphoide is True


def test_la_negation_ne_deborde_pas_de_sa_phrase():
    """La garde de négation regardait quarante-cinq signes sans se soucier de
    la ponctuation, et elle a nié une coque qui existait :

        « …manipuler vos écrans SANS retirer les gants
          Protections: COQUE RIGIDE AUX ARTICULATIONS pour une sécurité… »

    Le « sans » appartenait à la phrase sur l'écran tactile, deux rubriques
    plus haut. Une garde qui déborde de sa phrase se met à mentir dans l'autre
    sens — et celui-là fait BAISSER la couverture, ce qui le rend, pour une
    fois, presque visible.
    """
    t = ("Cuir e-touch et cuir conducteur pour manipuler vos écrans sans retirer "
         "les gantsProtections: Coque rigide aux articulations pour une sécurité "
         "renforcée")
    assert lire("", t).coque_articulations is True


# =============================================================================
# LES LIMITES DE MOT, ET LA PROSE SANS PONCTUATION
# =============================================================================

def test_performance_n_est_pas_une_perforation():
    """« Coutures hautes PERFORMANCES pour une solidité maximale sur route »,
    sur un gant de cuir de cerf qui n'a pas un seul trou.

    « performance » est un des mots les plus employés du rayon : écrit
    `perfor\\w*`, il faisait passer pour ventilés des gants d'hiver pleins.
    C'est le même accident que l'ABS des casques qui matchait « absorption »,
    à ceci près qu'ici les limites de mot ne suffisent pas — il faut écrire la
    terminaison.
    """
    t = ("Paume en cuir de cerf naturel A Plus, teinté tambour aniline "
         "Coutures hautes performances pour une solidité maximale sur route")
    assert lire("", t).ventilation is None
    assert lire("", "Paume à une seule couche avec perforation de trou laser "
                    "cartographiée.").ventilation is True


def test_la_manchette_collee_a_la_rubrique_suivante():
    """Le marchand qui écrit le plus colle ses rubriques sans espace :
    « Double serrage poignetMANCHETTE LONGUESoufflet aux articulations ».

    Un `\\b` en fin de motif échoue là-dessus : entre « longue » et « Soufflet »
    il n'y a pas de limite de mot, seulement une majuscule. Trois cent
    quatre-vingt-onze gants avaient perdu leur manchette, et le total ne le
    disait pas — il disait seulement « treize virgule six pour cent ».
    """
    assert lire("", "Double serrage poignetManchette longueSoufflet aux "
                    "articulations").manchette == "longue"
    assert lire("", "Les \"+\": Manchette mi-longueEmpreinte en tissu "
                    "conducteur").manchette == "mi-longue"
    assert lire("", "Paume renforcée en fibre d'aramideLes \"+\": Manchette "
                    "moyenneSerrage poignet").manchette == "mi-longue"
    # Et la garde continue de refuser ce qu'un `\b` refusait.
    assert lire("", "Manchette longueur réglable par tanka").manchette is None


def test_le_renfort_colle_a_la_rubrique_precedente():
    """Le même accident à l'ENTRÉE du mot : « Protection des phalanges en TPR
    injectéeRENFORT PAUME en SEESOFT ». Et la garde doit rester assez étroite
    pour ne pas matcher au milieu d'un mot."""
    assert lire("", "Protection des phalanges en TPR injectéeRenfort paume en "
                    "SEESOFT").renfort_paume is True
    assert lire("", "Un parenfort paume imaginaire").renfort_paume is None


def test_le_titre_de_rubrique_n_est_pas_une_phrase():
    """« Protection et RENFORTS » est un titre de rubrique, « Paume en
    NANOFRONT japonais » la ligne suivante, et le gant n'a aucun renfort de
    paume. Sans ponctuation entre les deux, seule la préposition manquante
    distingue le sommaire de la phrase."""
    t = ("Conçu pour la saison été afin d'optimiser le confort Protection et "
         "renforts Paume en NANOFRONT japonais offrant un grip")
    assert lire("", t).renfort_paume is None
    assert lire("", "Renforcement de la paume en cuir offrant une meilleure "
                    "résistance").renfort_paume is True


# =============================================================================
# CE QUI RESSEMBLE À DE L'ÉTANCHÉITÉ, ET CE QUI N'EN EST PAS
# =============================================================================

def test_impermeabilise_n_est_pas_impermeable():
    """« En peau de chèvre teintée dans la masse IMPERMÉABILISÉE conjuguée au
    microfibre », sur un gant d'été ajouré dont le nom dit « AIR ».

    Un cuir imperméabilisé résiste dix minutes à la pluie. Le vendre comme un
    gant étanche, c'est promettre à l'acheteur une sortie d'hiver au sec.
    """
    t = ("Gants à la manchette courte : En peau de chèvre teintée dans la masse "
         "imperméabilisée conjuguée au microfibre")
    assert lire("", t).impermeable is None
    assert lire("", "Dos de la main en Softshell reconnu pour ses propriétés "
                    "coupe-vent et déperlante").impermeable is None
    assert lire("", "Membrane HIPORA imperméable et coupe-vent pour garder les "
                    "mains au sec sous la pluie").impermeable is True


def test_le_gore_tex_lamine_n_est_pas_le_gore_tex_a_doublure_flottante():
    """Le marchand en fait trois valeurs, et la troisième n'est pas un détail
    de vocabulaire : un Gore-Tex laminé est collé à la matière extérieure, un
    Gore-Tex « Z-liner » pend entre deux couches, et les mains ne restent pas
    sèches de la même façon."""
    assert lire("", "Membrane imperméable et respirante Gore-Tex Z-liner. "
                    "Doublure tri-polaire push-pull.").gore_tex == "oui"
    assert lire("", "Membrane laminée GORE GRIP TEX imperméable et respirante "
                    "offrant un meilleur feeling").gore_tex == "oui, laminé"
    # Et « laminé » loin de la membrane ne parle pas d'elle : « Protection des
    # articulations en cuir laminé » est une pièce de cuir.
    assert lire("", "Membrane Gore-Tex. Paume en cuir de chèvre. Doublure en "
                    "Jersey coton. Protection des articulations en cuir laminé. "
                    "Manchette courte.").gore_tex == "oui"


def test_la_doublure_n_est_pas_toujours_thermique():
    """Trois doublures de gants d'ÉTÉ, sur trois marchands différents :

        « Doublure de confort en coton »
        « Doublure intérieure 100% polyester »
        « Doublure en tissu jersey, doux et confortable »

    Les compter comme thermiques aurait fait passer des gants d'été pour des
    gants d'hiver, et la couverture aurait doublé.
    """
    for phrase in (
        "Paume en cuir suédé synthétique Doublure: Doublure de confort en coton",
        "Doublure intérieure 100% polyester apportant un contact doux",
        "En textile synthétique, extensible Doublure: En tissu jersey, doux et "
        "confortable",
    ):
        assert lire("", phrase).doublure_thermique is None, phrase
    assert lire("", "Doublure thermique en Ouate idéale "
                    "l'hiver").doublure_thermique is True
    assert lire("", "Isolation thermique Thinsulate. Empiècements "
                    "extensibles").doublure_thermique is True


def test_la_sensibilite_tactile_n_est_pas_l_ecran_tactile():
    """« Doté du Sensor System pour une SENSIBILITÉ TACTILE optimale » et
    « INDICE TACTILE intelligent » parlent du ressenti au guidon — l'inverse
    exact du sujet. On exige donc qu'un écran ou un téléphone soit nommé à
    portée."""
    assert lire("", "Doté du Sensor System pour une sensibilité tactile "
                    "optimale").tactile is None
    assert lire("", "* Indice tactile intelligent * Construction super "
                    "flex").tactile is None
    assert lire("", "Index compatible avec écrans tactiles").tactile is True
    assert lire("", "Cuir tactile spécial sur le pouce et l'index permettant "
                    "l'usage du Smartphone").tactile is True


# =============================================================================
# L'UNIVERS DE PRATIQUE, ET LES NOMS PROPRES QUI LE POLLUENT
# =============================================================================

def test_racing_dans_un_nom_de_marque_n_est_pas_un_gant_racing():
    """Trois fabricants de tout-terrain ont « Racing » dans leur nom, et un
    marchand écrit la même formule de catalogue sur tous leurs gants :

        « Gants CROSS … Paire de gants MX … GANTS RACING premium. »

    Ce gant ne verra jamais un circuit. Le classer « sport » aurait rempli la
    caractéristique la plus attendue du configurateur avec le rayon cross au
    complet — et c'est précisément celle dont on ne peut pas se tromper, parce
    que c'est elle qui compose le panier.
    """
    t = ("Gants cross Evo 2.0 bleu gris orange L-10 Paire de gants MX Evo 2.0. "
         "Gants racing premium.")
    assert lire("", t).univers is None


def test_le_nom_de_modele_n_est_pas_un_univers():
    """« Gants hiver Ixon Pro CUSTOM en cuir de chèvre » est un nom de modèle,
    et « Protection articulations ADVENTURE injectée » un nom de pièce. Le mot
    d'univers doit suivre « gant(s) » avec, entre les deux, rien d'autre qu'une
    saison ou un genre — un nom propre s'y glisse, et la détection tombe."""
    assert lire("Gants cuir/textile Ixon Pro Custom noir- 3XL",
                "Gants hiver Ixon Pro Custom en cuir de chèvre.").univers is None
    assert lire("", "Paume en Cuir de chèvre. Protection articulations Adventure "
                    "injectée. Système anti-retournement.").univers is None


def test_l_univers_reel_est_bien_lu():
    """Sinon la garde ne sert qu'à tout refuser."""
    assert lire("", "Gant été racing. Dos en cuir de chèvre perforé.").univers == "sport"
    assert lire("", "RST vous propose ses gants moto Touring été homme les "
                    "VENTILATOR-X").univers == "touring"
    assert lire("", "Les gants Axys sont idéals pour un usage urbain pendant la "
                    "mi-saison").univers == "roadster"
    assert lire("", "Gants Tout Terrain 2.5 WINDBLOCK: Matière: En textile "
                    "supérieur WindBlock").univers == "enduro"


# =============================================================================
# LA SAISON, LE GENRE, ET LE DOUTE
# =============================================================================

def test_deux_saisons_dans_un_texte_font_zero_saison():
    """« Gants d'HIVER ou de MI-SAISON pour les navetteurs urbains » ne permet
    de classer nulle part. On ne tranche pas à la place du marchand."""
    t = ("Gants d'hiver ou de mi-saison pour les navetteurs urbains * Isolation "
         "primaLoft pour une protection optimale")
    assert lire("", t).saison is None


def test_le_participe_passe_n_est_pas_une_saison():
    """« Ces gants ONT ÉTÉ conçus pour la route » : c'est le verbe être. La
    saison n'est donc reconnue que collée à « gants », ou précédée de « d' »."""
    assert lire("", "Ces gants ont été conçus pour la route").saison is None
    assert lire("", "Gants été femme. Structure 4 Way Spandex.").saison == "été"
    assert lire("Gants de moto d'hiver imperméables à l'eau chauffés",
                "").saison == "hiver"


def test_un_gant_chauffant_n_est_pas_declare_gant_d_hiver():
    """Aucun gant chauffant ne se porte en juillet, mais le marchand en fait
    une CATÉGORIE à part, pas une saison. La déduction appartient à celui qui
    affichera la fiche, pas à celui qui la lit."""
    lu = lire("Gants chauffants Keis G301", "Les gants moto chauffants Keis G301")
    assert lu.chauffant is True
    assert lu.saison is None


def test_le_cable_chauffant_n_est_pas_un_gant_chauffant():
    """Le rayon contient les accessoires : « Câble pour VÊTEMENT CHAUFFANT de
    connexion batterie moto » n'est pas un gant, c'est un câble."""
    t = ("Câble pour vêtement chauffant DE CONNEXION BATTERIE MOTO: Les \"+\": "
         "Set de connexion batterie Jeu de fusibles Câble Y")
    assert lire("", t).chauffant is None


def test_deux_genres_dans_un_texte_font_zero_genre():
    """Deux mentions dans le même texte ne font pas un gant mixte : elles font
    un texte qu'on n'a pas compris. « Enfant », en revanche, l'emporte — un
    gant cross enfant est d'abord un gant d'enfant."""
    assert lire("", "Gants moto femme CRISSY").genre == "femme"
    assert lire("", "gants pour homme et pour femme").genre is None
    assert lire("Gants cross enfant Evo 2.0 noir/blanc- L-6", "").genre == "enfant"


def test_le_doute_rend_rien():
    """La règle qui gouverne tout le fichier. Un `None` n'écrit aucune ligne en
    base ; une caractéristique fausse coûte la confiance."""
    vide = lire("", "")
    assert vide.renseignees() == 0
    assert vide.matiere is None and vide.homologation is None
    # Un texte qui ne dit rien d'exploitable ne doit rien produire non plus.
    muet = lire("Gants cross Kinetic K220 midnight/bleu/orange- M/9",
                "Gants cross Kinetic K220 confortable et résistant.")
    assert muet.matiere is None
    assert muet.univers is None
    assert muet.homologation is None


# =============================================================================
# LA FUSION
# =============================================================================

def test_fusion_le_premier_qui_sait_repond():
    """L'appelant passe les marchands du plus disert au plus avare."""
    disert = lire("", "Manchette courte. Paume en cuir de chèvre.")
    avare = lire("", "Index compatible avec écrans tactiles.")
    out = fusionner([disert, avare])
    assert out.manchette == "courte"
    assert out.matiere_paume == "cuir"
    assert out.tactile is True


def test_fusion_un_desaccord_de_norme_ne_vaut_pas_mieux_qu_un_silence():
    """Deux marchands qui se contredisent sur une donnée de sécurité ne valent
    pas mieux qu'aucune source. En revanche « CE » et « EN 13594 » ne se
    contredisent PAS : le second précise le premier, et c'est lui qu'on garde.
    """
    un = lire("", "Homologués CE EN 13594:2015 niveau 1 KP")
    deux = lire("", "Homologués CE.")
    assert fusionner([un, deux]).homologation == "EN 13594"
    assert fusionner([deux, un]).homologation == "EN 13594"

    a = Gant(niveau="1")
    b = Gant(niveau="2")
    assert fusionner([a, b]).niveau is None


def test_fusion_cuir_contre_textile_on_abandonne():
    """La tentation est d'en conclure « cuir et textile » — les deux marchands
    auraient chacun vu une moitié. Mais c'est une déduction, pas une lecture,
    et elle se trompe exactement dans le cas où l'un des deux s'est trompé.

    « cuir et textile » contre « cuir », en revanche, n'est pas un désaccord :
    c'est le marchand qui a vu les deux matières et celui qui n'en a nommé
    qu'une.
    """
    assert fusionner([Gant(matiere="cuir"), Gant(matiere="textile")]).matiere is None
    assert fusionner([Gant(matiere="cuir"),
                      Gant(matiere="cuir et textile")]).matiere == "cuir et textile"
