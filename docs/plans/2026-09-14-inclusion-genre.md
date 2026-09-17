# Plan — « aucune information sur le genre » n'est pas « un autre genre »

Statut : **proposé, non appliqué.** Constaté le 2026-09-14 sur un cas signalé
par la propriétaire : `/recherche?q=Ixon+madden`.

## Le cas, en entier

La veste de pluie Ixon Madden donne **six fiches** pour ce qui est, au plus,
trois produits (jaune, noire, et la coupe « C-sizing »).

Le jaune, codes-barres `36616152769xx` — **la même veste, ses sept tailles** :

```
  ...951  S    FC-Moto + La Bécanerie   → fiche 18970   genre H-A
  ...968  M    FC-Moto + La Bécanerie   → fiche 18970   genre H-A
  ...982  XL   FC-Moto + La Bécanerie   → fiche 18970   genre H-A
  ...975  L    La Bécanerie seule       → fiche  4975   genre U-A   ← séparée
  ...999  2XL  La Bécanerie seule       → fiche  4975   genre U-A   ← séparée
  ...002  3XL  La Bécanerie seule       → fiche  4975   genre U-A   ← séparée
  ...019  4XL  La Bécanerie seule       → fiche  4975   genre U-A   ← séparée
```

FC-Moto déclare `male` dans son flux ; La Bécanerie ne déclare rien. Les tailles
que FC-Moto vend deviennent donc « homme », les autres restent « genre inconnu »
— et le genre entre dans l'`identity_hash`. Deux fiches.

La coupe C-sizing se coupe exactement pareil (`U-A` pour les tailles vendues par
La Bécanerie seule, `F-A` pour celles où FC-Moto déclare `female`).

**C'est le même défaut structurel que le cas Arai** : un marchand de plus devrait
enrichir une fiche, il la scinde. Seul le champ coupable change — ici le genre,
là-bas le nom du modèle.

## Ce qui existe déjà et ne suffit pas

`match.py` traite déjà `U` comme « aucune preuve » — mais **à l'intérieur d'un
code-barres** :

```sql
HAVING count(DISTINCT left(genre_age, 1)) FILTER (WHERE left(genre_age, 1) != 'U') > 1
```

et la résolution préfère un genre déclaré à `U`. Le problème apparaît **entre
codes-barres** : chaque taille a le sien, et l'absence d'information sur une
taille devient une différence au moment de former la fiche.

## La règle proposée

> Deux fiches dont tout est identique — marque, couleur, catégorie, année,
> modèle — et dont l'une porte `U` (genre inconnu) désignent le même produit.
> Le genre déclaré l'emporte.

Transposition exacte de la règle d'inclusion des couleurs, qui a tenu
(+2 644 fiches comparables, +13 sur-fusions sur 4 719).

Et elle est **plus sûre** que celle des couleurs : `U` ne veut pas dire
« unisexe », il veut dire « le flux n'a rien dit ». Il n'y a donc aucune
information à écraser. `U-E` (enfant) reste intouché : la moitié « âge » du
champ garde son verrou actuel, qui interdit toute fusion adulte/enfant.

## Portée mesurée (14/09/2026)

```
  2 803 groupes  /  7 060 fiches  séparées UNIQUEMENT par U contre H ou F
```

À comparer aux 1 541 fiches à taille unique visées par la règle des noms de
modèle : ce défaut-ci est plus large. À mesurer avant de livrer, comme les
autres : nombre de fiches devenues comparables, et sur-fusion.

## Ce qui reste NON couvert par cette règle

Le Madden **noir** se coupe pour une autre raison encore : Speedway ne vend que
la taille S et l'intitule « Noir Jaune Fluo », d'où une couleur `BK-YE|FLU`
contre `BK` chez les autres — la taille S part seule (fiche 94354, 4 marchands)
pendant que M→4XL restent ensemble (fiche 62123, 3 marchands).

La règle d'inclusion des couleurs existe déjà mais joue **dans** un groupe de
code-barres, pas au moment de former l'identité. L'étendre ici demande de la
prudence : entre deux codes-barres différents, `BK` contre `BK-WH` peut
parfaitement être deux coloris réellement différents du même blouson. Une mesure
brute donne 59 984 paires « couleur de l'une contenue dans l'autre », et ce
nombre **mélange les vrais éclatements et les vrais coloris** — il ne veut donc
rien dire tel quel. À segmenter avant d'en tirer quoi que ce soit.

## Recommandation

Les trois règles (modèle, genre, et plus tard la couleur) touchent le même
étage du calcul et **coûtent le même `match --reset` de 47 minutes**. Les
livrer ensemble, c'est une attente au lieu de trois.

---

## Mesure demandée : « et si on enlevait les filtres couleur et genre ? »

Question de la propriétaire le 14/09. Mesurée sur les offres vivantes, avec le
même comptage partout pour que les lignes soient comparables entre elles (mon
recomptage donne 25 607 là où `product_stats` affiche 27 234 — deux façons de
compter les marchands ; seuls les écarts entre lignes comptent ici).

| Si on… | fiches comparables | offres comparées | ce que ça casse |
|---|---|---|---|
| **aujourd'hui** | 25 607 | 172 027 | — |
| enlève le genre | 24 280 | 177 688 (+5 661) | fusionne homme et femme |
| enlève la couleur | 19 495 | 184 926 (+12 899) | fusionne le noir et le jaune |
| enlève les deux | 18 312 | 198 546 (+26 519) | les deux |
| **règle sûre** (genre inconnu absorbé par le genre déclaré) | 24 879 | **176 461 (+4 434)** | rien |

Plus, en quarantaine : sur 10 745 groupes bloqués (25 208 offres), **3 110
groupes / 8 210 offres** le sont *uniquement* à cause de la couleur ou du genre.

### Le contre-sens à ne pas faire

**Enlever un critère ne fait pas monter le catalogue, il le fait fondre.** Le
nombre de fiches comparables passerait de 25 607 à 18 312 : deux fiches
fusionnées n'en font plus qu'une. Ce qui monte, c'est le nombre d'offres
*rassemblées sur une même fiche* — et si le critère supprimé était légitime,
ces offres rassemblées sont des comparaisons **fausses** : le visiteur qui veut
le blouson noir se verrait proposer « le meilleur prix » du jaune.

C'est précisément la promesse que le site vend. Les +26 519 offres du scénario
« sans les deux » sont donc à lire comme un coût, pas comme un gain.

### Ce qui reste vrai

Le gain honnête est celui de la règle d'inclusion : **+4 434 offres comparées**
et **+59 fiches à trois marchands et plus**, sans une seule fusion abusive,
parce qu'on ne fusionne que là où un marchand n'a rien déclaré. Plus les 8 210
offres de quarantaine à réexaminer, dont une partie rejoindra ces fiches.
