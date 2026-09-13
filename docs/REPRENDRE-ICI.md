# Reprendre ici

Écrit le 2026-09-13 à 03h30, à la fin d'une longue session. Si tu ouvres une
session neuve sur ce projet, **lis ce fichier en premier**. Il dit ce qui est
vrai aujourd'hui, ce qui est cassé, et ce qu'il ne faut surtout pas faire avant
qu'une décision soit prise.

---

## 1. LA DÉCISION À PRENDRE AVANT TOUT LE RESTE

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
