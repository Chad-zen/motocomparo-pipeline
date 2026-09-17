# Reprendre ici

Écrit le 2026-09-13 à 03h30, à la fin d'une longue session. Si tu ouvres une
session neuve sur ce projet, **lis ce fichier en premier**. Il dit ce qui est
vrai aujourd'hui, ce qui est cassé, et ce qu'il ne faut surtout pas faire avant
qu'une décision soit prise.

---

## 0. CE QUI A CHANGÉ LE 2026-09-14 — à lire avant le reste

Session autonome longue. Le détail est dans
`docs/plans/2026-09-14-session-autonome.md` ; voici ce qui change la façon de
travailler sur le projet.

### Deux tâches planifiées existent maintenant
- **« MotoComparo - relevé des prix »**, 03h30 — `ops/prix_quotidien.cmd` :
  `fetch → load → normalize → signature → freshness`. C'est elle qui rend vraie
  la phrase « prix actualisés quotidiennement », qui n'était tenue par rien.
- **« MotoComparo - codes promo »**, 07h00 — `ops/promo_quotidien.cmd`.
- ⚠️ Les deux sont en « Interactive only » : elles ne tournent que session
  Windows ouverte. Les passer en « même si l'utilisateur n'est pas connecté »
  demande le mot de passe Windows.

### Trois pièges qui ont coûté cher, et qui se reproduiront
1. **Une règle de catégorie ajoutée ne s'applique pas toute seule.**
   `categorize` ne classe que les chemins marchands *jamais vus*. Après avoir
   touché `_RULES`, il FAUT `mcpipe categorize --remap`, sinon la règle neuve ne
   change rien et la commande dit quand même « ok ».
2. **L'empreinte d'identité est écrite à trois endroits dans `match.py`** et
   elles doivent rester identiques. L'une avait perdu `category_id` : sans
   conséquence tant qu'elle n'était qu'informative, mais elle a rendu une passe
   entière silencieusement inopérante le jour où quelqu'un s'en est servi.
3. **`refresh_product_stats()` n'était appelée nulle part**, alors que sa propre
   définition disait « appelée à la fin de freshness ». Tous les prix des listes
   venaient d'une vue jamais rafraîchie. Elle est appelée maintenant : ne pas la
   retirer.

### Le site dit maintenant la vérité sur lui-même
Plusieurs phrases affichées étaient fausses et vérifiables en trois clics par
n'importe quel visiteur (« 6 marchands vérifiés » alors que deux n'apparaissaient
sur aucune fiche ; « marchands français » alors que FC-Moto est allemand ; « un
prix de plus de 24 h n'est pas affiché » alors qu'il l'est, avec une étiquette).
Les chiffres se lisent désormais en base. **Ne jamais réécrire en dur un nombre
que la base connaît.**

### Le formulaire de lettre hebdomadaire est retiré
Il collectait des adresses sans pouvoir envoyer quoi que ce soit ni permettre la
désinscription — et le code de sa propre route l'interdisait par écrit tant que
la page de confidentialité n'existe pas. À remettre quand les trois manquent :
un envoi, une désinscription, une politique de confidentialité.

### `/admin` est verrouillé
Mot de passe si `ADMIN_MDP` est posé dans `.env`, sinon réseau local seulement.

### Table de travail à supprimer un jour
`essai_unites` sert au banc d'essai des règles de rapprochement pour ne pas
repayer vingt minutes de construction à chaque essai. Elle n'entre dans aucune
requête du site. `python ops/essai_replis.py --nettoyer` quand les règles sont
figées.

---

---

## 1. LA DÉCISION EST PRISE — 2026-09-13

**Le site v2 est autonome. Il ne dépend pas de WordPress.**

Décidé par l'exploitante le 2026-09-13, après consultation de deux seniors qui
recommandaient tous deux de quitter WordPress pour le catalogue. Elle va plus
loin qu'eux : ils proposaient de garder WordPress pour le blog et les pages
éditoriales derrière un reverse proxy ; elle ne veut aucune dépendance.

Conséquence directe et acceptée : **le site v2 doit fournir son propre tableau
de bord**, faute de quoi chaque changement de texte passerait par un
développeur. C'est le chantier « administration » ci-dessous, et il fait
désormais partie du périmètre.

Ce que ça rend caduc :

- `docs/publish-contract.md` — décrit comment alimenter WordPress. **Obsolète.**
  Gardé comme archive : il documente ce que la v1 attendait, ce qui reste utile
  pour comprendre les 70 extraits.
- `docs/architecture.md`, section « Publish » — le `RENAME` atomique vers MySQL
  n'aura pas lieu.
- Roadmap phases 4 et 6 — à réécrire : déploiement et redirections, pas
  `publish`.

Ce que ça ne change pas : le pipeline, les règles métier, les redirections 301
(~18 000 anciennes pages doivent fusionner quoi qu'il arrive).

## 1bis. L'ANCIENNE ALTERNATIVE, pour mémoire

**Deux architectures de publication coexistent dans ce dépôt et se contredisent.**

| | |
|---|---|
| **A — `publish` vers WordPress** | Décrit en détail dans `docs/architecture.md` et `docs/publish-contract.md`. Construit `wp_pc_*_next` dans la base MySQL du site, puis bascule atomique. Prévu par les phases 4 et 6 du roadmap. **Jamais écrit.** |
| **B — le site v2 lit PostgreSQL en direct** | `src/mcsite/`, écrit le 2026-09-13, fonctionne. Plus rien à recopier, pas d'étape `publish`, pas de limite de 120 s, retour arrière immédiat. |

Si B est retenu, `publish-contract.md` devient caduc et les phases 4 et 6 du
roadmap changent de sens. Si A est retenu, le site de `src/mcsite/` devient un
outil de visualisation interne.

**Tant que ce n'est pas tranché par écrit, construire l'un ou l'autre peut être
du travail jeté.** Les deux fichiers concernés portent maintenant un
avertissement en tête.

Éléments pour décider :

- La base MySQL de production est à **97 % de son quota de 3 Go** (91 Mo libres).
  Le catalogue v2 pèse 500-600 Mo. Voir `docs/infrastructure.md`.
- Un VPS Ubuntu 24.04 est en service depuis le 2026-09-13 (adresse dans `.env`,
  jamais commitée). **Rien n'y est déployé.**
- Le site WordPress v1 est toujours en ligne, son trafic est quasi nul.
- Le thème et une vingtaine d'extraits d'affichage v1 sont bons et réutilisables
  seulement dans le scénario A.

---

## 2. CE QUI EST CASSÉ, ET CONNU

### Deux défauts introduits le 2026-09-13, non corrigés

Décrits en détail dans `docs/plans/2026-09-13-taille-par-gtin.md` :

1. **Le garde-fou de l'emprunt de taille rate 109 cas.** Il bloque un marchand
   qui réutilise *un* code-barres, pas *plusieurs* codes-barres aboutissant à la
   même taille chez le même marchand. Le contrôle manquant doit tourner **après
   `match`**, pas dans `enrich`.
2. **Une taille empruntée écrase la taille déclarée par le marchand, pour
   toujours.** `coalesce(ovr.size_code, nullif(s.size_code, ''), 'TU')` place
   l'emprunt en premier. L'ordre correct est
   `coalesce(nullif(s.size_code, ''), ovr.size_code, 'TU')`. Un mot à changer.

### Défaut 3 — le catalogue est éclaté : le même produit sur plusieurs fiches

Trouvé le 2026-09-13 vers 04h, en comparant une fiche à la page du marchand.

Le casque Arai SZ-R VAS EVO bleu mat existe en **deux fiches** :

| fiche | tailles |
|---|---|
| `arai-evo-r-sz-vas-bl-mat-ad048414` | S |
| `arai-evo-r-solid-sz-vas-bl-mat-5cfda3d` | XS, M, L, XL |

Même modèle, même couleur, mêmes marchands. La coupure tient à **un mot** :
`Solid`. Il est présent dans le titre de certaines offres et pas d'autres,
il entre dans `model_tokens`, donc dans `identity_hash`, donc l'identité diffère.
Idem pour le blanc mat et pour le XL du noir mat.

C'est le **miroir exact du bug de méga-fusion** déjà décrit dans
`docs/roadmap.md` : les deux viennent du sac de jetons du modèle. L'un
agglomère, l'autre découpe. Celui-ci va dans le sens prudent — rien de faux
n'est mélangé — mais il produit des fiches à une seule taille et casse la
comparaison.

Ordre de grandeur, mesuré en groupant par (préfixe de 8 caractères de la
référence fabricant, marque, couleur, catégorie) :

| | |
|---|---|
| Familles coupées en plusieurs fiches | **9 540** |
| Fiches concernées | **32 633** |
| Pire famille | **223 fiches** |

⚠️ **Majorant, pas un fait.** Deux produits réellement différents peuvent partager
les 8 premiers caractères de leur référence. Le chiffre demande une vérification
par échantillon avant d'être cité. Le cas Arai, lui, est vérifié à la main.

Piste : un mot qui n'apparaît que chez un marchand sur trois n'est probablement
pas un mot du modèle. Un jeton présent dans moins de la moitié des titres d'un
même code-barres pourrait être écarté de l'empreinte. **À mesurer avant
d'implémenter** — toute modification de `model_tokens` touche l'appariement, donc
plan validé d'abord.

### Cinq dettes, par ordre de gravité

Listées dans `docs/plans/run_2026-09-13.md`. La plus grave de loin :

**`raw_offer.last_seen` est posé quand `normalize` tourne, pas quand le flux a
été téléchargé.** Retraiter un fichier vieux de trois jours marque toutes les
offres comme fraîches. Ça contamine `is_live`, donc les prix affichés, le
comptage des retraits, **et l'éligibilité des donneurs de taille**.

---

## 3. CE QUI MARCHE AUJOURD'HUI

```
mcpipe fetch → load → normalize → signature → categorize → enrich → match → verify → freshness
```

Dernier run complet : 2026-09-13, 02h32 → 03h16.

| | |
|---|---|
| Produits | 244 748 |
| Comparables (2+ marchands) | 24 590 |
| Avec un prix d'appel | 213 214 |
| `verify` | **0 anomalie** |
| Variantes sans taille | 44,5 % |
| File de revue | 17 548 (sain : c'est le refus de fusionner à tort) |

Le site : `.venv/Scripts/python.exe run_site.py`, puis http://127.0.0.1:8000

Il tourne au premier plan : la fenêtre reste occupée tant qu'il sert, `Ctrl+C`
l'arrête. Lancé depuis une session d'assistant, il meurt avec elle — donc le
relancer en début de session.

⚠️ **Couper le site avant de lancer `match`.** Il garde des connexions ouvertes et
`match` a besoin d'un verrou exclusif. Un incident antérieur a bloqué la base
2 heures pour cette raison.

⚠️ **Après tout `enrich`, lancer `match --reset`, jamais `match` seul.** La
consigne est affichée par l'outil ; elle a été ignorée le 2026-09-13 et a produit
un produit à cheval sur deux catégories. Un verrou d'état reste à écrire.

---

## 4. MESURE À REFAIRE

L'effet de l'emprunt des tailles n'est **pas attribuable** : le run du 13/09 a
mélangé deux variables — données neuves et code neuf. Le −74 produits
comparables a été élucidé (250 rétrogradés par des retraits marchands, ~176
gagnés), mais le reste ne l'est pas.

`offer_size_override` étant une table à part, la mesure propre reste faisable à
froid, sans retélécharger : vider la table, mesurer, la remplir, remesurer.

---

## 5. RÈGLES DE TRAVAIL DURES

- **Une fausse fusion coûte 10 à 50 fois plus cher qu'une fusion ratée.** Dans le
  doute, quarantaine, jamais de devinette.
- **Mesurer avant, mesurer après**, sur une photo figée. Un chiffre sans
  comparaison ne prouve rien.
- **Segmenter avant de s'alarmer.** Trois fausses alertes ont été tuées par la
  question « ventile par catégorie ».
- **Une seule session tient la base à la fois.**
- Sofia fait les commits. Rien n'est poussé sans son accord.
- Aucune mention d'IA ni de vrai nom dans les commits — dépôt portfolio.
- **Inclusion sur les noms de modèle** — un marchand moins bavard scinde une taille sur sa propre fiche (cas Arai SZ-R VAS EVO mesuré le 2026-09-13). Plan : `docs/plans/2026-09-13-inclusion-modele.md`. Coût : `match --reset`, 47 min.

## Cadence des flux — relevé en cours

`ops/cadence_flux.py` échantillonne la date de publication des six flux toutes
les 15 minutes pendant 24 h (lancé le 2026-09-14). Requêtes `HEAD` uniquement :
aucun fichier téléchargé, aucun lien d'affiliation suivi.

    python ops/cadence_flux.py --resume

donne le nombre réel de republications par marchand. C'est ce chiffre qui décide
combien de relevés de prix programmer par jour — un par republication, pas un de
plus. Premier indice : Motoblouz a republié en pleine matinée, donc sa cadence
n'est visiblement pas quotidienne.

## ⚠️ PASSAGE EN ATTENTE — à lancer, dans CET ordre

Trois correctifs sont écrits, testés et mesurés, mais **aucun n'est visible** :
ils demandent un recalcul des signatures puis un `match`.

```
mcpipe signature          # 3 min  — le tiret collé (« BNS TECH-2 » → taille 2)
mcpipe enrich             # 1 min  — catégories + emprunt des tailles au code-barres
mcpipe match --reset --sans-mpn   # 47 min — site ARRÊTÉ
python ops/appliquer_mpn.py       # 1 min
mcpipe freshness                  # 3 min  — obligatoire, sinon aucun prix
mcpipe verify
```

Ce que ce passage apporte, mesuré le 2026-09-14 :

| | |
|---|---|
| tailles empruntées au code-barres | 14 023 → **33 067** |
| offres reclassées de catégorie | **43 400** |
| fausses tailles « génération » (TECH-2, GT-Air) | **39 216** supprimées |

## L'ORDRE DES ÉTAPES — trois erreurs commises le 2026-09-14

**`signature` → `enrich` → `match`.** Aucune de ces trois n'est optionnelle et
l'ordre n'est pas décoratif.

1. **`match` ne recalcule PAS les signatures.** Un correctif sur les tailles ou
   les couleurs reste sans effet tant que `mcpipe signature` n'a pas tourné.
   Coûté une fois : un `match` lancé pour rien, coupé après une minute.
2. **`enrich` porte l'emprunt des tailles au code-barres** (`borrow_sizes`), pas
   seulement les catégories, et doit tourner AVANT `match` — ce sont les
   variantes qui figent les tailles. Oublié le 14/09 : les emprunts dataient de
   la veille.
3. **Toute étape qui réécrit une table en masse doit l'ANALYZER** avant de
   rendre la main. Trois pannes le même jour, toutes de cette cause :
   `freshness` 39 min au lieu de 2 ; la passe préfixe **50 min sans finir** (le
   planificateur croyait `product` vide après le TRUNCATE du `--reset`) ;
   `_BUILD_GTIN_UNITS` 31 min au lieu de 24 après un `signature` sans ANALYZE.
   Corrigé dans `match.py` et `signature.py`. **Reste à vérifier pour
   `normalize` et `load`.**

## La preuve l'emporte sur la supposition

Signalé par Sofia le 14/09/2026, et c'est une règle générale, pas un cas isolé.

Une taille lue dans un TITRE ou une URL est une inférence : on prend le mot qui
occupe la place où une taille se trouve d'habitude. Ce que deux marchands
déclarent dans leur FLUX sur le même code-barres est une preuve.

Le code faisait l'inverse par accident : le titre étant lu en premier, l'offre
n'était plus vide, et l'emprunt au code-barres la sautait. Corrigé dans
`enrich.py` — l'emprunt écrase désormais aussi une taille d'origine `title` ou
`url`. **À se demander pour chaque champ** : la couleur et le genre ont la même
structure (flux, puis titre) et n'ont pas été vérifiés.

## ⚠️ À LANCER — accord des marchands sur un même code-barres

La découpe du rayon « Protections » (2026-09-14) a introduit une régression :
elle lisait le titre de CHAQUE offre séparément, alors que les marchands ne
nomment pas la même chose pareil.

    Speedway  « Tour De Nuque Alpinestars BNS Tech-2 »     -> rayon 28
    Motoblouz « Protection cervicale Alpinestars BNS »      -> rayon 28
    FC-Moto   « Alpinestars BNS Tech-2 Protecteur de cou »  -> aucun mot-clé, 11

Même code-barres (8033637210797), deux rayons. Le rayon entre dans l'identité
d'une fiche : le pipeline a vu un conflit et a détaché les trois. Une fiche à
sept marchands est tombée à un.

Correctif écrit (`accorder_protections_par_gtin`, branché dans `mcpipe enrich`)
et **mesuré à blanc** : 2 352 offres ralliées, désaccords de rayon 13 547 →
12 353. Il applique la règle que le projet suit déjà pour les casques — le
sous-type est emprunté au voisin qui partage le code-barres avant que le titre
soit cru.

    mcpipe enrich                      # 1 min
    mcpipe match --reset --sans-mpn    # 46 min, site ARRÊTÉ
    python ops/appliquer_mpn.py        # 1 min
    mcpipe freshness                   # 2 min

Les 12 353 désaccords restants sont ANTÉRIEURS : des marchands qui rangent déjà
le même code-barres dans des rayons différents. Chantier à part, non ouvert.

## La recherche : l'index est posé, la requête ne sait pas encore s'en servir

**Fait le 2026-09-14** (`sql/016_recherche_trigrammes.sql`, appliqué) :

- `f_unaccent()`, enveloppe IMMUTABLE d'`unaccent` — sans elle PostgreSQL
  refuse d'indexer l'expression ;
- un index GIN de trigrammes sur
  `f_unaccent(model_display || ' ' || brand_code)`, **30 Mo, construit en 2 s**.

Vérifié : une recherche écrite sous forme POSITIVE contre cette expression
répond instantanément, là où le balayage prenait 0,15 s par mot et par requête
de facette.

**Ce qui reste à faire, et c'est le vrai gain.** La clause `_OU` demande
aujourd'hui « *aucun* mot n'est absent » — une négation (`NOT EXISTS` sur un
`unnest`) que l'index ne peut pas servir. Il faut la retourner en une
conjonction de conditions POSITIVES, une par mot :

```sql
AND (f_unaccent(model||' '||brand) ILIKE '%mot1%' OR p.category_id = ANY(<ids>))
AND (f_unaccent(model||' '||brand) ILIKE '%mot2%' OR p.category_id = ANY(<ids>))
```

Trois points d'attention :

1. `_OU` est une CONSTANTE interpolée dans huit f-strings (`queries.py` lignes
   627, 636, 644, 667, 687, 714, 868, 876). Elle doit devenir une fonction
   `_ou(f)` puisque le nombre de conditions dépend du nombre de mots (≤ 4).
   `_args(f)` fournit alors `q0..q3`.
2. Les rayons dont le libellé correspond au mot doivent être résolus en un
   `ARRAY(SELECT id FROM category WHERE …)` **non corrélé** — sinon la
   sous-requête se réexécute par ligne et annule le bénéfice.
3. Le `OR p.category_id = ANY(…)` a besoin d'un **index sur
   `product(category_id)`** pour que PostgreSQL combine les deux branches
   (BitmapOr). `product_lookup_idx` commence par `brand_code` : il ne sert pas.

**Vérification obligatoire après réécriture** : comparer le NOMBRE DE RÉSULTATS
avant/après sur une dizaine de recherches réelles (« arai sz », « casque »,
« ixon madden », « gants cuir »). Une recherche qui rend moins de résultats sans
qu'on s'en aperçoive est pire que lente.

**Pourquoi ce n'est pas fait le 14/09** : décidé à 22h15 de ne pas réécrire
l'entrée principale du site en fin de journée. Le gain est réel (11,5 s au
premier appel), mais il n'est pas urgent : le cache applicatif ramène déjà les
appels suivants à 0,01 s, et nginx (`proxy_cache_background_update`) fera
disparaître l'attente même au premier, une fois sur le VPS.
