"""Caractéristiques lues sur le web : deux agents, puis un dernier contrôle."""

from __future__ import annotations

from mcpipe import importer_web as w


def _ext(champ="saison", valeur="hiver"):
    return [{"product_id": 1, "trouve": {champ: {"valeur": valeur, "preuve": "x", "url": "https://x/y"}}}]


def _ver(confirme=True, valeur="hiver", citation="Gants d'hiver chauffants", champ="saison"):
    return [{"product_id": 1, "champ": champ, "valeur": valeur, "confirme": confirme,
             "citation_exacte": citation}]


def test_une_valeur_confirmee_et_soutenue_par_le_passage_est_retenue():
    retenues, refusees = w.preparer(_ext(), _ver())
    assert len(retenues) == 1 and not refusees


def test_une_valeur_non_confirmee_est_refusee():
    retenues, refusees = w.preparer(_ext(), _ver(confirme=False))
    assert not retenues and refusees[0][2] == "non confirmée par le second agent"


def test_une_valeur_absente_de_la_verification_est_refusee():
    assert w.preparer(_ext(), [])[0] == []


def test_le_second_agent_doit_confirmer_la_meme_valeur():
    retenues, _ = w.preparer(_ext(valeur="hiver"), _ver(valeur="ete", citation="usage estival"))
    assert not retenues


def test_un_passage_sans_rapport_avec_la_valeur_est_refuse():
    retenues, refusees = w.preparer(_ext(), _ver(citation="Livraison offerte dès 69 euros"))
    assert not retenues and "ne contient pas la valeur" in refusees[0][2]


def test_une_fiche_exclue_a_la_main_n_est_jamais_ecrite():
    retenues, refusees = w.preparer(_ext(), _ver(), exclure={1})
    assert not retenues and refusees[0][2] == "exclue à la main"


def test_les_mots_de_preuve_des_saisons():
    assert w.passage_soutient("saison", "ete", "Veste idéale pour l'été")
    assert w.passage_soutient("saison", "toutes-saisons", "Toutes saisons")
    assert not w.passage_soutient("saison", "hiver", "Veste d'été aérée")
    assert not w.passage_soutient("saison", "hiver", "")


def test_une_classe_d_homologation_exige_la_norme_dans_le_passage():
    assert w.passage_soutient("homologation", "A", "Certifié EN 17092 classe A")
    assert not w.passage_soutient("homologation", "A", "Veste textile renforcée")
    assert w.passage_soutient("homologation", "EN 13594", "gants homologués EN 13594")
