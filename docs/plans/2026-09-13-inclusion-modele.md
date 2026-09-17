# Plan — un nom de modèle moins bavard n'est pas un autre modèle

Statut : **proposé, non appliqué.** Constaté le 2026-09-13 sur un cas signalé
par la propriétaire. Même forme que `2026-09-13-inclusion-couleur.md`, qui est
appliqué et a tenu.

## Le cas, en entier

Recherche « Arai sz », couleur bleu mat : **deux fiches pour le même casque**,
l'Arai SZ-R VAS EVO Solid. Les cinq codes-barres sont ses cinq tailles.

```
  ...809  XS   FC-Moto + Motoblouz              → fiche 59047
  ...823  M    FC-Moto + Motoblouz              → fiche 59047
  ...830  L    FC-Moto + Motoblouz              → fiche 59047
  ...847  XL   FC-Moto + Motoblouz              → fiche 59047
  ...816  S    FC-Moto + Motoblouz + Speedway   → fiche 109712   ← isolée
```

Speedway intitule le casque « Casque Arai SZ-R VAS Evo Bleu Mat », **sans le mot
« Solid »** ; les deux autres écrivent « SZ-R VAS EVO SOLID ». Le nom du modèle
étant déduit des titres des membres du groupe, celui-ci retient :

```
  evo · r · sz · vas            au lieu de   evo · r · solid · sz · vas
```

Jetons différents → `identity_hash` différent → fiche séparée.

## Ce qui rend le défaut grave

**C'est le marchand SUPPLÉMENTAIRE qui casse le regroupement.** La taille la
mieux couverte est celle qui se retrouve seule. Un marchand de plus devrait
enrichir une fiche, jamais la scinder — ici l'effet est exactement inverse, et
il s'aggrave à mesure que le catalogue grandit.

## La règle proposée

> Deux noms de modèle dont l'un est **contenu** dans l'autre, à marque, couleur,
> genre, catégorie et année identiques, désignent le même produit. Le plus
> complet l'emporte.

`{evo, r, sz, vas} ⊆ {evo, r, solid, sz, vas}` → compatible, retenir le second.
`{evo, r, sz, vas}` contre `{evo, r, sz, vas, 5g}` → à mesurer : un suffixe peut
être une génération, donc un autre produit. **C'est le point à trancher avant
d'écrire une ligne.**

C'est la transposition exacte de la règle d'inclusion des couleurs, qui a rendu
+2 644 fiches comparables sans bouger la sur-fusion (+13 sur 4 719).

## Portée attendue

Cette même mécanique est la cause probable des **1 541 fiches à taille unique**
relevées dans `ops/mesure_catalogue.py` (`eclat_fiches_1_taille`) : chaque taille
a son propre code-barres, et il suffit d'un titre plus court chez un marchand
pour qu'une taille parte seule.

## Avant d'appliquer — à mesurer

1. **Combien de paires** de produits ont des jetons de modèle en relation
   d'inclusion, à marque / couleur / genre / catégorie / année identiques ?
2. **Quelle est la nature des mots ajoutés ?** Dépouiller les cent cas les plus
   fréquents. Si le mot en plus est un qualificatif (`solid`, `mono`, `matt`),
   l'inclusion est sûre. Si c'est une génération ou une référence (`2`, `ii`,
   `5g`, `evo`), elle ne l'est pas — et il faudra une liste d'exclusion.
3. **Les codes-barres consécutifs** : les cinq EAN du cas ci-dessus ne diffèrent
   que par leur dernier chiffre. C'est une piste indépendante et peut-être plus
   sûre que les jetons — à quantifier avant de choisir.

## Coût et règle d'arrêt

Un `match --reset` complet : **47 minutes**, site arrêté. Mesure avant/après avec
`ops/mesure_catalogue.py`, et la règle qui a servi ce soir :

> Si la sur-fusion bouge (`fusion_ratio_gte_5`, `fusion_ratio_gte_20`,
> `fusion_pire_nb_gtin`, `fusion_ecart_prix_x10`, `coherence_violations`), on
> revient en arrière. Gagner des comparables en réunissant des produits
> différents coûte 10 à 50 fois plus cher que rater une fusion.
