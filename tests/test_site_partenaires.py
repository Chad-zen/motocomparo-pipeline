"""Les bannières partenaires : ce qui ne doit jamais glisser.

Ces règles ne se voient pas en regardant une page : elles se voient le jour où
elles ont été enfreintes, et il est alors trop tard. Elles sont donc tenues ici.
"""

from __future__ import annotations

from mcsite import partenaires


def test_chaque_banniere_a_un_lien_de_suivi_et_une_image():
    for p in partenaires.PARTENAIRES:
        assert p["clic"].startswith("https://"), p["code"]
        assert p["image"].startswith("https://"), p["code"]
        assert p["nom"], p["code"]


def test_les_identifiants_de_suivi_sont_tous_differents():
    """Deux bannières partageant un identifiant, c'est un marchand payé pour
    les clics d'un autre — et personne ne s'en apercevrait avant la facture."""
    clics = [p["clic"] for p in partenaires.PARTENAIRES]
    assert len(set(clics)) == len(clics)


def test_seuls_des_marchands_du_comparateur_sont_annoncés():
    """Annoncer un marchand qu'on ne compare pas brouille la promesse du site.
    La liste est celle des six marchands du catalogue."""
    connus = {"speedway", "labecanerie", "motoblouz", "maxxess", "motoaxxe", "fcmoto"}
    for p in partenaires.PARTENAIRES:
        assert p["code"] in connus, p["code"]


def test_par_defaut_l_image_ne_vient_pas_de_la_regie():
    """Le pixel de mesure de la régie est désactivé par défaut : c'est lui qui
    obligerait à recueillir le consentement des visiteurs, et qui rendrait faux
    ce que la page « À propos » promet."""
    assert partenaires.EMPREINTE_REGIE is False
    for b in partenaires.bandeaux():
        assert "effi.show" not in b["image"], b["code"]


def test_le_lien_de_suivi_reste_celui_de_la_regie():
    """On enlève le pixel, jamais le lien : c'est lui qui rémunère."""
    for b in partenaires.bandeaux():
        assert "effi.click" in b["clic"] or "pkw.motoblouz.com" in b["clic"], b["code"]
