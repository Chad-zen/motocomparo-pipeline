# Codes promo — le relevé automatique, repris de la v1

*2026-09-13.*

L'exploitante a rejeté la saisie manuelle que j'avais construite : « je veux ce
qu'il y avait sur la v1, y a un tracker qui vient vérifier les codes promo chez
les sites des marchands ». Il existait bien.

## Ce que la v1 faisait vraiment

Extrait **« MC Codes Promo v1 - codes promo marchands »**, greffon *Code
Snippets* (id 171, actif, 809 lignes de PHP). Il contient trois sources, et
c'est son histoire qui compte :

1. **Effinity** (`apiv2.effiliation.com`) — codé, toujours dans le fichier,
   **plus jamais appelé**.
2. **Kwanko** — pareil, mort.
3. **Les pages promo publiques des marchands** — la seule que la tâche
   quotidienne appelle encore : `mc_promo_sync_all()` ne fait plus qu'une chose,
   `mc_promo_scan_sites()`.

Autrement dit, l'exploitante avait raison de mémoire : les plateformes
d'affiliation servaient des codes périmés, et la v1 a fini par aller lire la
page du marchand, comme un client le ferait.

Le reste du mécanisme, repris tel quel :

- une liste de motifs **notés** (« avec le code X » vaut 40, « CODE X » tout seul
  vaut 10, parce que ce dernier attrape aussi « CODE POSTAL ») ;
- une **liste noire** de mots français écrits en capitales à côté du mot « code »
  (LIVRAISON, CADEAUX, CGV…) — le résidu d'un an de faux positifs ;
- l'exclusion des codes de **bienvenue / newsletter / parrainage**, qui exigent
  un compte ou une première commande et n'ont donc rien à faire sur une fiche ;
- le **retrait automatique** : un marchand qui termine une opération retire
  simplement sa bannière, sans jamais écrire « terminé ». Disparaître de la page
  est le seul signal de fin de vie que ces codes reçoivent.

## Ce qu'on a corrigé au passage

**La v1 affichait un code périmé depuis six mois.** Sa lecture des dates prenait
la *première* date trouvée autour du code. Or une page promo est une **liste** :
celle de Speedway aligne une douzaine d'opérations passées, chacune écrite
« … valable jusqu'au : 2026-03-18 … Avec le code SPEED15 ». Chaque code héritait
donc de la date de l'offre imprimée en haut de page.

Trois conséquences, mesurées le 13/09/2026 :

- le format ISO de Speedway (`jusqu'au : 2026-03-18`) n'était reconnu par aucun
  motif de la v1 — donc aucune date du tout ;
- `SPEED15` et `FRENCH`, expirés en mars et en mai, étaient servis comme actifs
  (visibles sur motocomparo.com le jour de l'analyse) ;
- Motoblouz écrit « du **1er** Septembre » et « du **Mardi** 23 Juin 2026 » :
  ni l'ordinal ni le jour de la semaine n'étaient lus.

La v2 rattache donc à chaque code **la date la plus proche de lui dans le
texte**, et sait lire les quatre écritures rencontrées. Vérifié sur les pages
réelles : Speedway n'a aujourd'hui **aucun code en cours** — toutes ses dates
sont passées —, et c'est la réponse honnête.

## État de chaque marchand (13/09/2026)

| Marchand | Page | Résultat |
|---|---|---|
| Motoblouz | `code-promo-motoblouz.html` | ✅ `BACK26` (au 13/09), `CFS26` (au 14/02/2027) |
| Speedway | `/code-promo` | lue, mais **archive** : aucune offre en cours |
| Maxxess | `/blog/code-promo-maxxess/` | lue, aucun code en cours |
| Moto-Axxe | `/bons-plans/` | lue, aucun code en cours — l'URL de la v1 (`/blog/code-promo-moto-axxe/`) renvoie 404 depuis, la boutique a déplacé ses offres |
| La Bécanerie | `/code-promo.html` | ❌ **403 Cloudflare**, même sur `robots.txt` |
| FC-Moto | — | absent de la v1 aussi (site allemand, pas de page promo française) |

**La Bécanerie ne sera pas contournée.** Le blocage est une protection que la
boutique a choisie ; on ne la déjoue pas. Deux issues honnêtes : ses codes se
saisissent à la main dans le tableau de bord (`source = 'manuel'`, qu'aucun
relevé n'écrase), ou le relevé se lance depuis le serveur de production — la v1
lisait cette page sans problème depuis la machine Hostinger, le blocage vise
peut-être seulement cette IP.

## Ce qui a été écrit

- `src/mcpipe/promo.py` — le relevé (lecture, extraction, dates, conditions,
  écriture, retrait).
- `sql/013_code_promo_tracker.sql` — `source`, `vu_le`, `conditions`, `contexte`.
  Appliquée.
- `mcpipe promo` — la commande. Indépendante des étapes catalogue : elle ne
  touche ni une offre ni un produit, donc elle tourne site allumé.
- `tests/test_promo.py` — 24 tests, dont chaque faux positif historique.
- Fiche produit : les conditions et la date de validité s'affichent sous le
  libellé, comme sur la v1.
- Tableau de bord : chaque code indique son origine (relevé / saisi).

## À faire

- **Planifier `mcpipe promo` une fois par jour** (la v1 : WP-Cron, `daily`).
- Réessayer La Bécanerie depuis le serveur de production.
- Un code sans date lisible reçoit une échéance de 14 jours, repoussée tant
  qu'il reste affiché. À surveiller : si un marchand publie sans jamais dater,
  c'est ce délai qui décide, et il est arbitraire.

---

# La fiche produit sur grand écran (même journée)

« Retravaille la version desktop des fiches produits, elles sont différentes. »
Le volet d'aperçu réduit une page de 1280 px à ~255 px de large : l'œil ne
tranche pas. Les deux fiches ont donc été **mesurées** à 1280 px, bloc par bloc.

| | v1 | v2 avant | après |
|---|---|---|---|
| grille du haut | 440 / 631 | 380 / 682 | 440 / 622 |
| bloc « meilleur prix » | 631 (toute la colonne) | **520** | 622 |
| titre h1 | 631 | **244** (bridé à 22ch) | 622 |
| les 4 garanties | grille 2 × 306, haut. 43 | **1 colonne**, haut. 120 | 2 × 302, haut. 56 |
| tuiles de confiance | 4 × 276 | **absentes** | 4 × 274 |

Les trois écarts venaient de règles que je m'étais accordées seul, toutes dans
le même bloc `@media (min-width: 1150px)` : brider le titre à 22 caractères et
le bloc prix à 520 px « pour le confort de lecture ». Résultat : un vide à
droite du bloc sombre, sur la seule zone que le visiteur regarde. Supprimées.

Les quatre tuiles de bas de page (« Prix vérifiés », « Marchands français »,
« Aucun surcoût », « Sans inscription ») n'existaient pas dans la v2 : leur
texte a été relevé sur la v1 et le bloc reconstruit. Attention au nom : la
classe `.confiance` était **déjà prise** par le bandeau en haut de toutes les
pages, et la réutiliser transformait ce bandeau en grille de quatre colonnes
sur tout le site. Renommée `.garanties`. C'est la troisième collision de ce
type (`.tuile`, `.bandeau`) : une classe nouvelle se vérifie avant d'être posée.

Vérifié après coup : 7 pages en 200, 99 tests au vert, aucun débordement
horizontal à 375 px, et le bandeau du haut de nouveau à 35 px sur toutes les
pages.

## La même fiche à 1024 px — ce que les captures montraient vraiment (14/09)

Les deux captures comparées par la propriétaire sont prises en **mode
ordinateur** sur son téléphone. Vérifié : la v1 *est* adaptative (à 375 px elle
passe en une colonne, bouton pleine largeur), donc ses captures ne sont pas la
v1 « mobile » — elles sont sa mise en page large, à **1024 px**. C'est la
largeur à laquelle il fallait comparer, et trois écarts y restaient :

| | v1 @1024 | v2 avant | après |
|---|---|---|---|
| titre h1 | 27 px | **21 px** | 27 px |
| bloc « meilleur prix » | 110 px de haut, sur une rangée | **175 px**, bouton empilé | 110 px, sur une rangée |
| bouton « Voir l'offre » | 144 × 48, à droite du prix | **415 px pleine largeur** | 130 × 48, à droite du prix |
| rond comparateur | 42 px, dans la rangée | absolu, flottant au coin | 42 px, dans la rangée |
| les 4 garanties | 13,5 px | 15 px | 13,5 px |

Le piège était là : j'avais relevé « titre 21 px » et « bouton pleine largeur »
sur une capture **étroite** de la v1, puis figé ces valeurs à toutes les
largeurs. Or la v1 change les deux en passant en deux colonnes. Les règles sont
donc bornées à `min-width: 1000px`, et sous cette largeur la fiche garde le
comportement téléphone — vérifié à 390 px : titre 21 px, bouton pleine largeur,
garanties en 2 × 2, aucun débordement horizontal.

### Pourquoi « rien n'avait changé » chez elle (14/09)

Le mode ordinateur de Chrome Android rend la page à **980 px**, pas 1024. Mes
règles étaient bornées à `min-width: 1000px` : elles ne se déclenchaient donc
jamais sur son téléphone, et la fiche restait exactement comme avant. Corrigé à
900 px, le seuil où la v1 bascule elle-même (mesuré : 1 colonne à 900, deux
colonnes et titre 27 px à 940).

Le bloc prix passe aussi en `flex-wrap` plutôt qu'en seconde requête média :
c'est ce que fait la v1, dont la rangée se replie toute seule quand la colonne
devient trop étroite (110 px de haut à 980, 174 px à 940 chez elle).

Vérifié après correction : 980 px → titre 27 px, bloc 110 px, bouton 130 × 48 à
droite du prix, garanties en 4 colonnes ; 880 px → retour à l'empilé et au titre
21 px ; 390 px → inchangé, aucun débordement.

**Leçon** : une largeur de test choisie « au hasard » (1024) n'est pas la
largeur du terrain. Chrome Android = 980 px en mode ordinateur.
