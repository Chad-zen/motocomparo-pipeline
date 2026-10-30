from mcsite import analyse
from mcsite.analyse import indicateurs, profil


def _par_cle(contenu):
    return {i["cle"]: i for i in indicateurs(contenu)}


def test_indicateurs_d_un_modele_teste_et_pese():
    c = {"securite": {"sharp_etoiles": 5, "date_test": "Septembre 2024", "norme": "ECE 22.06"},
         "fiche_technique": [
             {"nom": "Poids", "valeur": "1 500 g (pesée SHARP)", "source": "SHARP"},
             {"nom": "Norme", "valeur": "ECE 22.06", "source": "SHARP"},
             {"nom": "Pinlock", "valeur": "Pinlock 120 fourni", "source": "x"}]}
    i = _par_cle(c)
    assert i["sharp"]["etoiles"] == 5
    assert i["poids"]["valeur"].endswith(" g") and 45 <= i["poids"]["pct"] <= 55
    assert i["poids"]["detail"] == "Pesé en test"
    assert i["norme"]["ok"] is True
    assert i["pinlock"]["type"] == "oui"


def test_ce_qu_on_n_a_pas_n_est_pas_montre():
    """Regle de la proprietaire (22/10/2026) : si on n'a pas, on ne mentionne pas."""
    assert _par_cle({"fiche_technique": []}) == {}
    i = _par_cle({"fiche_technique": [
        {"nom": "Pare-soleil", "valeur": "Non intégré ; système compatible", "source": "x"},
        {"nom": "Pinlock", "valeur": "Non fourni", "source": "x"}]})
    assert "pare_soleil" not in i and "pinlock" not in i      # un manque n'est pas une case
    assert all(x["type"] != "inconnu" and x["type"] != "non" for x in indicateurs({}))


def test_un_poids_annonce_dit_d_ou_il_vient():
    i = _par_cle({"fiche_technique": [{"nom": "Poids annoncé", "valeur": "1 250 g", "source": "x"}]})
    assert i["poids"]["detail"] == "Annoncé par le constructeur"


def test_le_curseur_de_profil_va_de_urbain_a_sportif():
    assert profil({}) is None                                  # pas de position, pas de curseur
    assert profil({"profil_curseur": {"position": 95}})["libelle"] == "Sportif"
    assert profil({"profil_curseur": {"position": 50}})["libelle"] == "Enduro / trail"
    assert profil({"profil_curseur": {"position": 6}})["libelle"] == "Urbain"
    assert profil({"profil_curseur": {"position": 400}})["position"] == 100


def test_le_curseur_de_coque_range_les_matieres():
    from mcsite.analyse import coque_curseur

    def cran(valeur):
        k = coque_curseur([{"nom": "calotte", "valeur": valeur}])
        return k["cran"] if k else None

    assert cran("polycarbonate") == 1        # contient « carbon » : ne doit PAS passer au carbone
    assert cran("thermoplastique") == 1
    assert cran("fibre") == 2
    assert cran("composite") == 3
    assert cran("carbone") == 4
    assert cran("Carbon Kevlar") == 4
    assert cran("Carbon-Glass Hybrid") == 3
    assert coque_curseur([]) is None and cran("bois") is None     # inconnu : pas de curseur


def test_la_fiche_verifiee_prime_sur_la_caracteristique_des_flux():
    from mcsite.analyse import coque_curseur
    contenu = {"fiche_technique": [{"nom": "Coque", "valeur": "Composite de fibres (technologie Arai PB-cLc2)"}]}
    k = coque_curseur([{"nom": "calotte", "valeur": "thermoplastique"}], contenu)
    assert k["cran"] == 3 and k["technologie"] == "PB-cLc2"


def _carac(**kw):
    return [{"nom": k, "valeur": v} for k, v in kw.items()]


def test_l_analyse_automatique_ne_dit_que_ce_qui_est_releve():
    from mcsite.analyse import analyse_auto
    a = analyse_auto(_carac(homologation="22.06", pinlock="fourni", ecran_solaire="True",
                            interieur_amovible="True", calotte="carbone"), "helmet.integral")
    cles = {i["cle"] for i in a["indicateurs"]}
    assert {"norme", "pinlock", "pare_soleil", "doublure"} <= cles
    assert "Écran solaire intégré" in a["points_forts_courts"] and len(a["points_forts_courts"]) == 4
    assert a["profil"]["position"] == 68 and a["profil"]["auto"] is True


def test_l_analyse_automatique_se_tait_quand_il_y_a_trop_peu():
    from mcsite.analyse import analyse_auto
    assert analyse_auto(_carac(ventilation="True"), "helmet.jet") is None        # moins de trois cases
    a = analyse_auto(_carac(homologation="22.05", pinlock="fourni", interieur_amovible="True"), "helmet.jet")
    assert a is not None and a["points_forts_courts"] is None or len(a["points_forts_courts"]) >= 3
    # un intercom « fourni » n'est jamais traduit en case : seul « prepare » l'est
    b = analyse_auto(_carac(intercom="fourni", homologation="22.06", pinlock="fourni", interieur_amovible="True"), "helmet.jet")
    assert "audio" not in {i["cle"] for i in b["indicateurs"]}


def test_coque_la_premiere_matiere_fait_foi_pas_les_versions_carbone():
    # LS2 FF811 / FF901 / OF603 : « Fibre de verre (HPFC), versions carbone » n'est pas du carbone
    assert analyse._cran_coque("Fibre de verre (HPFC), versions carbone") == 2
    assert analyse._cran_coque("Thermoplastique (KPA) avec éléments en carbone 6K") == 1
    assert analyse._cran_coque("Carbone 6K") == 4


def test_coque_deux_matieres_selon_la_version_est_indeterminee():
    assert analyse._cran_coque("Carbone (versions Carbon) ou fibre de verre (HPFC)") is None


def test_un_modele_a_deux_matieres_dit_carbone_pour_une_version_carbon():
    """LS2 OF603 « CARBON URUS » affichait « fibre de verre HPFC » : le texte vaut pour tous les coloris (24/10/2026).
    Sofia (29/10/2026) : « si c'est ecrit carbon c'est carbon » : le titre tranche."""
    contenu = {
        "accroche": "Un jet LS2 en HPFC avec pare-soleil intégré. Deux entrées d'air sur le dessus.",
        "description": "Coque HPFC légère. Doublure lavable.",
        "points_forts_courts": ["Coque légère en fibre de verre HPFC", "Pare-soleil intégré"],
        "fiche_technique": [{"nom": "Coque", "valeur": "Fibre de verre (HPFC), versions carbone"},
                            {"nom": "Norme", "valeur": "ECE 22.06"}],
    }
    assert analyse.coque_mixte(contenu) is True
    carbon = analyse.contenu_selon_titre(contenu, "Casque jet LS2 OF603 INFINITY II - CARBON URUS")
    assert [(l["nom"], l["valeur"]) for l in carbon["fiche_technique"]] == [("Coque", "Carbone"), ("Norme", "ECE 22.06")]
    assert carbon["points_forts_courts"] == ["Pare-soleil intégré"]
    assert "HPFC" not in carbon["description"] and "HPFC" not in carbon["accroche"]
    assert carbon["accroche"] == "Deux entrées d'air sur le dessus."
    # les coloris unis gardent le texte
    assert analyse.contenu_selon_titre(contenu, "Casque jet LS2 OF603 INFINITY II - SOLID") is contenu
    # un modele a une seule matiere n'est pas « mixte » ; son titre sans « carbon » ne le touche pas
    simple = {"fiche_technique": [{"nom": "Coque", "valeur": "Thermoplastique (KPA)"}]}
    assert analyse.coque_mixte(simple) is False
    assert analyse.contenu_selon_titre(simple, "Casque SOLID") is simple


def test_un_point_fort_selon_les_versions_rend_le_modele_mixte():
    """HJC RPHA 91 : la ligne « Coque » est muette, le point fort dit « carbone, verre, lin selon les versions »."""
    contenu = {"fiche_technique": [{"nom": "Coque", "valeur": "Composite de fibres (technologie PIM Evo)"}],
               "points_forts": [{"texte": "Coque PIM Evo en fibres (carbone, verre, lin selon les versions)."}]}
    assert analyse.coque_mixte(contenu) is True
    carbon = analyse.contenu_selon_titre(contenu, "Casque modulable HJC RPHA91 CARBON - LAGOS")
    assert carbon["fiche_technique"][0]["valeur"] == "Carbone"


def test_les_cases_de_l_essentiel_sont_recalculees_avec_la_coque_carbone():
    contenu = {"fiche_technique": [{"nom": "Coque", "valeur": "Fibre de verre (HPFC), versions carbone"},
                                   {"nom": "Norme", "valeur": "ECE 22.06"}]}
    contenu["indicateurs"] = analyse.indicateurs(contenu)
    assert any(i["cle"] == "coque" for i in contenu["indicateurs"])
    carbon = analyse.contenu_selon_titre(contenu, "OF603 CARBON URUS")
    case = [i for i in carbon["indicateurs"] if i["cle"] == "coque"]
    assert case and "carbone" in str(case[0]).lower()


def test_un_titre_carbon_donne_une_coque_carbone_meme_sur_un_modele_composite():
    """Sofia, 30/10/2026 : « si c'est ecrit carbon c'est carbon » ; mais « carbone/gris » et « Carbon Grey » sont des coloris."""
    contenu = {"fiche_technique": [{"nom": "Coque", "valeur": "Composite de fibres (verre, aramide)"}]}
    assert analyse.contenu_selon_titre(contenu, "Casque Shark Spartan GT Pro Carbon Ritmo")["fiche_technique"][0]["valeur"] == "Carbone"
    assert analyse.contenu_selon_titre(contenu, "Casque HJC RPHA12 Kos carbone/gris/jaune") is contenu
    assert analyse.contenu_selon_titre(contenu, "Casque X Carbon Grey") is contenu
