-- Distinguer une date de fin LUE d'une date de fin DEVINÉE.
--
-- Sans ça, le relevé du lendemain écrase une vraie échéance par son échéance
-- courte de secours dès que le marchand retire la date de sa bannière : le code
-- se voyait alors repoussé au-delà de sa vraie fin, tous les jours, sans jamais
-- mourir. La docstring promettait « une échéance courte, repoussée — jamais
-- l'inverse » ; c'est cette colonne qui le rend vrai.
ALTER TABLE code_promo
    ADD COLUMN IF NOT EXISTS fin_estimee boolean NOT NULL DEFAULT false;

-- Les lignes déjà relevées sans date lisible portaient l'échéance de secours :
-- on ne peut pas savoir après coup lesquelles, donc on ne réécrit rien. La
-- colonne part à `false`, et le premier relevé qui lit une vraie date remet
-- les compteurs à zéro.
