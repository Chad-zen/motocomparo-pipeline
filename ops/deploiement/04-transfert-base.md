# 04 — Transférer la base du PC vers le VPS

## Ce qu'on n'envoie PAS

Mesuré le 17/09/2026 : la base pèse **6,6 Go**, dont **2,7 Go de tables de
travail** qui n'ont rien à faire sur le VPS.

| table | taille | pourquoi on l'exclut |
|---|---|---|
| `stg_feed_row` | 2 531 Mo | Le déversoir brut des flux. `load` la **vide et la réécrit** à chaque relevé. La copier reviendrait à envoyer 2,5 Go qui seront effacés au premier passage. |
| `offer_signature_bak` | 170 Mo | Une sauvegarde prise à la main sur le PC. |

On exclut leurs **données**, pas leur structure (`--exclude-table-data`) : la
table doit exister, sinon le premier `load` échoue. C'est 41 % de moins à
téléverser, et c'est la seule partie du déploiement qui dépend de ta connexion.

> Une précaution : sur le VPS, `enrich` lit `stg_feed_row` pour la taxonomie
> Google de FC-Moto. Il ne faut donc pas lancer `enrich` seul avant qu'un `load`
> soit passé. Le relevé quotidien fait les deux dans l'ordre, rien à prévoir.

Les deux façons de transférer ; la première est plus simple, la seconde plus
rapide si la connexion est lente.

**Ne pas lancer ceci pendant un `match`** : la copie prendrait un catalogue à
moitié reconstruit. Attendre la fin, `freshness` compris.

## A. Copie directe (recommandée)

Sur le **PC**, dans PowerShell, à la racine du projet :

```powershell
# 1. Fabriquer l'archive. `-Fc` est le format compressé de PostgreSQL : il se
#    restaure en parallèle et pèse trois à quatre fois moins qu'un fichier SQL.
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" `
    --dbname=$env:DATABASE_URL --format=custom --compress=9 `
    --exclude-table-data=stg_feed_row `
    --exclude-table-data=offer_signature_bak `
    --file=mcpipe.dump

# 2. L'envoyer. Remplacer <IP> par l'adresse du VPS.
scp mcpipe.dump root@<IP>:/tmp/
```

Sur le **VPS** :

```bash
# 3. Restaurer. `--jobs=2` : le VPS a un cœur, mais la restauration alterne
#    entre disque et processeur — deux tâches se recouvrent utilement. Au-delà,
#    elles se gênent.
sudo -u postgres pg_restore --dbname=mcpipe --clean --if-exists \
     --no-owner --role=mcpipe --jobs=2 /tmp/mcpipe.dump

# 4. LES STATISTIQUES. Une base restaurée n'en a AUCUNE : le planificateur
#    travaille à l'aveugle et choisit des plans catastrophiques. C'est
#    exactement ce qui a fait tourner une passe 50 minutes sans finir le
#    2026-09-14. Cette commande n'est pas optionnelle.
sudo -u postgres vacuumdb --analyze-in-stages --dbname=mcpipe

# 5. Effacer l'archive : elle contient tout le catalogue.
rm -f /tmp/mcpipe.dump
```

## B. Par un tunnel, sans fichier intermédiaire

Utile si le disque du PC est juste, ou la connexion capricieuse : rien n'est
écrit nulle part, tout passe dans le tuyau.

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" `
    --dbname=$env:DATABASE_URL --format=custom --compress=9 `
    --exclude-table-data=stg_feed_row `
    --exclude-table-data=offer_signature_bak |
  ssh root@<IP> "sudo -u postgres pg_restore --dbname=mcpipe --clean --if-exists --no-owner --role=mcpipe"
```

Puis l'étape 4 ci-dessus, qui reste obligatoire.

## Vérifier que le transfert est complet

Sur le VPS :

```bash
sudo -u postgres psql -d mcpipe -c "
  SELECT 'fiches' AS quoi, count(*) FROM product
  UNION ALL SELECT 'offres vivantes', count(*) FROM raw_offer WHERE is_live
  UNION ALL SELECT 'avec un prix', count(*) FROM product WHERE min_price IS NOT NULL;"
```

Comparer aux mêmes chiffres sur le PC. Ils doivent être **identiques** — pas
proches. Un écart signifie une restauration partielle, et une restauration
partielle ne se voit pas à l'œil sur le site : elle se voit sur une fiche, un
mois plus tard, quand un visiteur la signale.

## Ce qui ne se transfère pas

- **`.env`** : recopié à la main (étape 03). Il contient les adresses des flux,
  avec leurs jetons d'affiliation.
- **Le dossier `feeds/`** : 925 Mo de CSV. Inutile de les transférer, le
  premier `mcpipe fetch` sur le VPS les téléchargera.
