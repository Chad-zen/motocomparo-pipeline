-- Les calculs que la propriétaire lance depuis l'administration.
--
-- Le site ne lance JAMAIS un calcul lui-même (son compte n'a pas le droit
-- d'exécuter autre chose que le site). Il écrit une demande ici ; un minuteur
-- système (`mcpipe taches`, chaque minute) l'exécute, en une seule tâche à la
-- fois, et y écrit le résultat. Seules les tâches de la liste blanche de
-- `mcpipe/taches.py` sont acceptées.
CREATE TABLE IF NOT EXISTS tache_demandee (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tache       text NOT NULL,
    statut      text NOT NULL DEFAULT 'demandee'
                CHECK (statut IN ('demandee', 'en_cours', 'terminee', 'echec')),
    demandee_le timestamptz NOT NULL DEFAULT now(),
    debut_le    timestamptz,
    fin_le      timestamptz,
    sortie      text
);
CREATE INDEX IF NOT EXISTS tache_demandee_statut_idx ON tache_demandee (statut, id);
