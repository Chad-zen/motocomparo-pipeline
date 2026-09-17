# Pourquoi des produits existants n'apparaissent pas — diagnostic du 17/09/2026

Signalé par la propriétaire : « des produits qui existent bien chez les
marchands mais qui ne sont pas listés chez nous », avec trois exemples. Ce
document ne change rien : il mesure. Les correctifs sont listés à la fin, avec
leur portée, pour être décidés un par un.

---

## 1. Shoei Neotec 3 — FC-Moto absent : ce n'est pas notre bug

FC-Moto vend bien le Neotec 3 sur son site. Son **flux** ne le contient pas.

Recherche sur les 270 Mo du fichier du jour (146 533 produits) :

| motif cherché | occurrences |
|---|---|
| `Neotec 3` / `NEOTEC 3` / `neotec-3` | **0** |
| code-barres `4512048807535` | **0** |
| référence `12070013` | **0** |

Nous ne pouvons lister que ce qu'un marchand publie. Rien à corriger de notre
côté ; c'est une remarque à faire à FC-Moto.

---

## 2. Les tailles Motoblouz sur cette fiche — un vrai manque, contournable

Les cinq tailles Motoblouz se replient en une seule ligne « taille non
communiquée » à 535,20 €. Trois raisons cumulées :

- **Le flux Motoblouz n'a aucune colonne de taille.** Vingt colonnes :
  `universal reference`, `name`, `price`, `crossed price`, `category`,
  `product url`, `image url`, `HAN`, `brand`… aucune ne porte la taille.
- **Le titre ne la porte pas non plus** : les cinq lignes s'appellent
  identiquement « Casque modulable Shoei NEOTEC 3 - FINITION BRILLANT ».
- **L'URL est un lien de tracking opaque** (`pkw.motoblouz.com/?P4122…`).

Le code-barres pourrait pourtant sauver la situation : Speedway porte
**exactement les cinq mêmes codes-barres**, avec les bonnes tailles. Mais
Speedway ne les déclare pas dans son flux — il les écrit dans son lien, sous
une forme explicite :

```
https://www.speedway.fr/329834-casque-shoei-neotec-3-blanc.html?channable=…#/taille-s
                                                                            ^^^^^^^^
```

Or `borrow_sizes()` refuse de relayer une taille d'origine `url` : « ne jamais
emprunter une supposition ». La règle est saine — mais ce marqueur n'est pas
une supposition, c'est une déclaration du marchand.

**Mesure de fiabilité** (22 604 paires code-barres où un `url` et un `feed`
décrivent le même article, codes-barres non réutilisés des deux côtés) :

| lecture | accord |
|---|---|
| brut | 65 % |
| après le repli canonique de `match` (`S5556` → `S`) | **85,6 %** |

Et les 14 % restants ne sont pas des contradictions : ce sont les notations de
FC-Moto — `2XL` contre `XXL`, `32` contre `3232`, `EU36` contre `3632`,
`2XS` contre `XXS`. Autrement dit, la même taille écrite autrement.

> Piège rencontré deux fois aujourd'hui : comparer des signatures BRUTES au lieu
> d'appliquer l'expression que `match` utilise réellement. La première mesure
> donnait 65 % et condamnait la piste.

**Gain potentiel si le marqueur `#/taille-xx` comptait comme déclaré :**
**9 839 offres sur 2 285 fiches.**

---

## 3. Furygan Waco — pas un bug

Les 38 offres sont toutes chargées. Elles ne se regroupent pas parce que **ce
ne sont pas les mêmes produits** :

| marchand | modèle | codes-barres |
|---|---|---|
| La Bécanerie | Waco (3 coloris) | `3435980296…`, `3435980318…` |
| Motoblouz | Waco **EVO 2** | `3435980349…` |

Deux modèles distincts d'une même famille. Les fusionner serait une erreur.
Restent 8 offres Maxxess / Moto-Axxe orphelines, qui relèvent du point 4.

---

## 4. Le vrai sujet : 153 455 offres vivantes rattachées à aucune fiche

Sur 763 908 offres vivantes :

| état | offres |
|---|---|
| rattachées à une fiche | 610 453 |
| `unresolved` — le match n'a pas su | **130 483** |
| `quarantined` — conflit d'identité sur le code-barres | **22 972** |

Soit **20 % du catalogue invisible**. Et ce n'est pas un retard : 146 791 de ces
orphelines datent du chargement initial du 11/09. Seules 6 038 sont arrivées
aujourd'hui et attendent légitimement le prochain `match`.

### Répartition des causes

| cause | offres | part |
|---|---|---|
| signature complète, jamais appariée | 79 419 | 51 % |
| marque inconnue | 69 545 | 45 % |
| pas d'identité calculée | 4 481 | 2 % |
| aucun jeton de modèle | 10 | 0 % |

**Marques inconnues — la part récupérable.** 178 marques inconnues apparaissent
chez **au moins deux marchands** : 35 751 offres, donc de vraies fiches
comparables. Les plus grosses : EK Chain (4 366 + 1 902 sous deux graphies),
Drag Specialties, Touratech, AFAM, RiderUnik, JT, PBR, Miller Exhaust,
Centauro, Namura, Troy Lee Designs, P2R, 100 %, Tour Max. 348 autres marques
n'ont qu'un marchand (33 794 offres) : les ajouter créerait des fiches sans
comparaison possible.

**Signature complète et pourtant orpheline — 79 419.**

| | offres |
|---|---|
| sans code-barres, mais avec une référence | 62 349 |
| **avec un code-barres** | **16 788** |
| ni l'un ni l'autre | 292 |

Les 16 788 sont les plus troublantes : produits parfaitement identifiés (veste
Ixon Asgard, casque HJC i91, sweat IXS Rapid), avec marque, rayon et
code-barres. **1 584 d'entre elles partagent même leur code-barres avec une
offre qui, elle, est rattachée à une fiche** — une incohérence franche.

**Quarantaine — 22 972 offres, 10 015 codes-barres.** Exemple typique, le
code-barres `3599180655225` chez quatre marchands :

| marchand | couleur lue | titre |
|---|---|---|
| Speedway | `SI` | Visière Shark Evoline Chrome Traité Antibuée |
| La Bécanerie | `CB-SI` | Ecran Shark Evoline Pro / Carbon / Evoline chrome miroir |
| Motoblouz | `CB` | Ecran casque Shark IRIDIUM - EVOLINE 3 / EVOLINE PRO |
| FC-Moto | `SI` | Shark Evoline Visière |

C'est le même écran. Nos lectures de couleur divergent (`CB` et `SI` sont
disjointes), l'identité ne concorde pas, et le code-barres entier est mis de
côté — quatre marchands perdus sur une fiche qui serait exemplaire.

---

## Ce qu'il y a à décider

Par rapport gain / risque, pas par ordre de découverte :

1. **Marques inconnues vues chez 2 marchands ou plus** — 35 751 offres. Le plus
   gros gain, le plus faible risque : on ajoute des noms à une liste.
2. **Marqueur `#/taille-xx` reconnu comme déclaré** — 9 839 offres, 2 285
   fiches. Risque faible, mesuré ci-dessus ; demande un `signature` + `enrich`
   + `relier-tailles`.
3. **Conflits de couleur en quarantaine** — 22 972 offres. Chantier à part :
   il faut comprendre pourquoi `CB` et `SI` sont lues sur le même écran avant
   de toucher à la garde.
4. **Les 16 788 orphelines à code-barres** — cause non encore identifiée.
   À instruire avant toute correction.

Les points 1 et 2 demandent ensuite un `match` complet (≈ 50 min, site éteint)
pour que les nouvelles fiches apparaissent.
