"""Les bannières partenaires : ce qui ne doit jamais glisser.

Ces règles ne se voient pas en regardant une page : elles se voient le jour où
elles ont été enfreintes, et il est alors trop tard. Elles sont donc tenues ici.
"""

from __future__ import annotations

from mcsite import partenaires


# Les domaines de suivi des deux régies. Une image servie depuis l'un d'eux
# n'est pas une image : c'est un pixel de mesure.
REGIES = ("track.effiliation.com", "pkw.motoblouz.com", "webgains", "ikhnaie")


def test_chaque_partenaire_a_un_lien_de_suivi():
    for p in partenaires.PARTENAIRES:
        assert p["clic"].startswith("https://"), p["code"]
        assert p["nom"], p["code"]


def test_aucune_image_affichee_ne_vient_d_une_regie():
    """LA règle, et elle a déjà été enfreinte une fois.

    Le 17/09/2026, la bannière Motoblouz pointait vers `pkw.motoblouz.com` —
    le domaine de suivi de Kwanko. Mesuré : quatre cookies posés pour 60 jours,
    à l'AFFICHAGE, chez un visiteur qui n'avait rien cliqué, avec
    « no consent mode activated » écrit dans la réponse par Kwanko lui-même.
    La page « À propos » promet exactement le contraire.

    Le commentaire du code disait « il n'y a pas de tiers supplémentaire » : vrai
    sur la forme, faux sur le fond. La question n'est pas de savoir s'il y a un
    tiers, c'est de savoir si un cookie part sans clic.

    Ce test ne lit pas les commentaires, il lit les adresses."""
    for p in partenaires.PARTENAIRES:
        for cle in ("image", "large"):
            url = p.get(cle)
            if not url:
                continue        # un partenaire sans visuel est écarté, pas affiché
            for regie in REGIES:
                assert regie not in url, f"{p['code']}.{cle} passe par {regie}"


def test_un_partenaire_sans_visuel_ne_sort_pas_de_la_rotation_a_vide():
    """Écarté, pas affiché vide : un emplacement publicitaire qui ne charge rien
    laisse un trou dans la page, et la mention « Publicité » au-dessus du trou."""
    for format in ("carre", "large"):
        for b in partenaires.bandeaux(format):
            assert b["image"], b["code"]


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
