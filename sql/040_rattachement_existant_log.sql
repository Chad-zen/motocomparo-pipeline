-- Les offres que `match` a rattachees a la fiche DEJA portee par leur code-barres.
--
-- POURQUOI. Le 20/10/2026, le `match` incremental ne construisait ses unites qu'avec les offres `unresolved` :
-- une offre neuve dont le code-barres etait deja rattache ailleurs fabriquait sa propre empreinte d'identite et,
-- si le nom differait d'un mot, creait une fiche isolee (Motoin : 15 298 fiches a un seul marchand dont les
-- codes-barres existaient chez les autres). `match.rattacher_a_la_fiche_existante` remplace maintenant, avant la
-- creation des fiches, l'empreinte de l'unite par celle de la fiche qui porte deja ce code-barres.
--
-- Cette table est le JOURNAL de ces rattachements, ecrit AVANT l'ecriture : de quoi les annuler (remettre les offres
-- d'une nuit `unresolved` puis relancer `match`, qui recalcule leur propre empreinte). La fonction la cree si elle manque :
-- cette migration ne fait que la documenter. Plafond tout-ou-rien : `MCPIPE_RATTACHER_MAX` (2 000 offres par passage).

CREATE TABLE IF NOT EXISTS rattachement_existant_log (
    raw_offer_id bigint PRIMARY KEY,
    gtin         text   NOT NULL,
    product_id   bigint NOT NULL,
    hash_propre  text   NOT NULL,
    nuit         date   NOT NULL DEFAULT current_date
);
