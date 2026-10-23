# La passe hebdomadaire : les nouveaux modèles de casques

Les fiches enrichies sont écrites par MODÈLE (403 modèles de 49 marques au 23/10/2026, 94 % des casques comparables).
Un modèle sorti après n'a pas de texte écrit : sa fiche affiche l'analyse automatique (au moins 3 cases tirées de ses
caractéristiques), ce qui est correct mais moins riche. Cette passe, une fois par semaine, rédige les modèles manquants.

## Le déroulé

1. **Lister le travail** : `bash ops/fiches/nouveaux_modeles.sh` donne, par marque, le nombre de fiches comparables
   sans texte. Prendre les marques où il y en a le plus ; `bash ops/fiches/nouveaux_modeles.sh agv` donne les modèles
   d'une marque.
2. **Exporter les données d'une marque** : `bash ops/fiches/export_marque.sh agv` crée `scratch/nouveaux/agv/` avec
   `fiches.csv`, `descriptions.csv`, `sharp.csv`, `revendeur.csv`, limités aux casques sans texte.
3. **Faire rédiger** : un rédacteur par marque (un agent par marque, en parallèle) avec
   `docs/fiches/consignes-redaction.md`. Il écrit `scratch/nouveaux/<marque>/fiches_enrichies.json`.
4. **Contrôler** : `python ops/fiches/audit_lot.py scratch/nouveaux` doit rendre 0 alerte (aucun marchand cité, aucun
   prix, aucune absence mentionnée, motifs bien écrits, matière de coque jamais contredite). Corriger à la main les
   alertes ; relire un échantillon de textes.
5. **Fusionner** dans les fichiers versionnés : `python ops/fiches/fusionner_lot.py scratch/nouveaux`, puis commit
   (`contenu/fiches_enrichies/`).
6. **Charger en production** : `git pull` sur le serveur puis `mcpipe fiches-enrichies --dossier contenu/fiches_enrichies`
   (relecture complète en quelques minutes, sans risque : c'est un upsert). La chaîne de nuit recharge de toute façon
   ce dossier chaque nuit, donc un `git pull` suffit si l'on n'est pas pressé. Aucun redémarrage du site n'est nécessaire.
7. **Vérifier** : la couverture sur la production
   (`SELECT count(*) FILTER (WHERE EXISTS (SELECT 1 FROM fiche_enrichie f WHERE f.brand_code = p.brand_code AND s.best_title ~* f.motif)), count(*) FROM product p JOIN product_stats s ON s.product_id = p.id WHERE p.category_id BETWEEN 1 AND 5 AND s.merchant_count >= 2`)
   et une ou deux fiches ouvertes à la main.

## Pièges connus

- Un motif de fiche s'écrit avec `\y` (limite de mot PostgreSQL), jamais `\b`. Dans le JSON : `\\y`.
- Un motif ne doit toucher que son modèle : tester contre `fiches.csv` ET contre les modèles déjà rédigés.
- Une matière de coque contredite sur la même page (composite d'un côté, carbone de l'autre) : voir la règle 6 des consignes.
- Aucun nom de marchand dans les textes ni dans les sources, jamais d'absence mentionnée (« non testé »).
- Un modèle qui n'a presque aucune donnée fiable ne se rédige pas : mieux vaut l'analyse automatique qu'un texte inventé.
