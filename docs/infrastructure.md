# Infrastructure — what is actually there

> **Les valeurs réelles ne sont PAS dans ce fichier.** Ce dépôt est public et
> volontairement anonymisé. Noms de bases, identifiants Hostinger, adresse IP,
> nom d'hôte et référence de paiement ont été remplacés par des marqueurs de la
> forme `<...>` le 17/09/2026, après un audit de sécurité. Les vraies valeurs se
> lisent dans hPanel et dans `.env`, qui n'est dans aucun dépôt.
>
> Elles restent lisibles dans l'historique git déjà publié : les retirer d'un
> commit ne les efface pas des précédents. Réécrire cet historique est une
> opération destructive sur un dépôt public — c'est une décision de la
> propriétaire, pas une décision technique.
>
> `tests/test_depot_anonyme.py` empêche désormais leur retour.

Measured 2026-09-13, read-only, from hPanel and from each site's WordPress
"Site Health → Info" page. Everything here was checked, not assumed: an earlier
version of these notes had the two databases the wrong way round and drew the
wrong conclusion from it.

## The two WordPress installs

There are **two** complete WordPress sites, not one.

| | production | staging |
|---|---|---|
| Address | `motocomparo.com` | `staging.motocomparo.com` |
| Database | **`<base-prod>`** | **`<base-staging>`** |
| Database size / quota | 2981 / 3072 MB (**97%**) | 3028 / 3072 MB (98.6%) |
| Database created | 2025-12-31 | **2026-09-05** |
| Table prefix | `wp_` | `wp_` |

Same theme (ReHub), same 18 active plugins, same 70 WPCode snippets, same
`MC Flux` v1 plugin. The staging is a full copy made on 2026-09-05.

⚠️ **`4MFbB` is the staging database, not production.** Notes written before
2026-09-13 call it "the main one" — they are wrong. A phpMyAdmin session opened
from the `4MFbB` row is looking at staging, and its MySQL user
(`<base-bac-a-sable>`) cannot see the production database at all. To reach
production, open phpMyAdmin from the **`8sMNw`** row (user `<user-prod>`).

## Disk is not a constraint. The per-database quota is.

| resource | used | limit | |
|---|---|---|---|
| Disk | 10.95 GB | 50 GB | 22% |
| Inodes (files) | 69,485 | 600,000 | 12% |
| Memory (avg) | 62 MB | 3072 MB | |
| CPU (avg) | 10% | 100% | |

So the plan is **Business Web Hosting**, and there is plenty of disk. The only
wall is that **each MySQL database is capped at 3072 MB**, and both live ones are
within ~50-90 MB of that cap.

Note: each site's WordPress reports a much larger "total installation size"
(13.07 GB for production, 7.55 GB for staging). Those figures overlap — hPanel's
10.95 GB is the authority. There is no hidden pile of leftover feed files; that
hypothesis was raised on 2026-09-13 and disproved the same day.

## A third database exists and is nearly empty

`<base-orpheline>` — 7 MB used, unattributed to any site, created 2026-01-02,
user `<user-orpheline>`. It carries its **own 3072 MB quota**.

The v2 catalogue is estimated at 500-600 MB. It would fit there with room to
spare, without deleting anything from production.

**Open question, not yet tested:** whether WordPress can read tables in a second
database. The MySQL host is the same (`127.0.0.1`), so cross-database queries are
possible in principle, but each Hostinger database has its own user and the
production user would need a grant on `X5EYI`. To be verified before relying on
it.

## The VPS

Provisioned 2026-09-13. This is where the v2 pipeline — and, as decided the same
day, the v2 site itself — will run.

| | |
|---|---|
| Host name | `<hote-vps>` |
| Plan | Hostinger KVM 1 (annual, paid) |
| Location | France |
| OS | Ubuntu 24.04 LTS, plain — no control panel |
| Extras | none: no malware scanner, no Docker manager (both declined to keep RAM for PostgreSQL; both can be added later from the VPS dashboard) |
| Expires | 2027-09-12 |
| IPv4 | `<ip-vps>` |
| IPv6 | `<ipv6-vps>` |
| Reverse DNS | `<hote-vps>` (les deux) |

Why 24.04 and not the 26.04 LTS offered as default: 24.04 is the mature LTS that
PostgreSQL's own apt repository and most tooling target. 26.04 was five months old
at the time of the decision. The OS can be reinstalled from hPanel if that proves
wrong.

Why a plain image and not one with a control panel: those install a web server and
a MySQL of their own, neither of which this project needs, and they take the memory
PostgreSQL wants on an entry-level plan.

## What this changes

1. **Cleaning the ~870,000 dead `wp_pc_catalog` rows is no longer a prerequisite
   for anything.** It was only ever about freeing space, and space has three
   other answers now (the VPS, the empty database, the 50 GB disk). The runbook
   stays in `ops/v1-menage-lignes-mortes.sql` for the day it is wanted — and
   note it must be pointed at `8sMNw`, not the database it was written against.
2. **There IS a staging environment.** Earlier notes said there was none and
   that every display snippet therefore had to be tested in production. That was
   wrong, and it removes the main risk hanging over the publish phase: the v2
   display can be built and broken on `staging.motocomparo.com` without a
   visitor or Google ever seeing it.
3. The publish target decision (`docs/architecture.md`: build `wp_pc_*_next` in
   the WordPress database, then an atomic swap) was **already made** and is not
   blocked by space. What remains genuinely undecided is whether a v2 product
   page is a WooCommerce post or a page rendered from our own tables — that is a
   question about `wp_posts` / `wp_postmeta` growth, not about disk.

## VPS de staging — mis en ligne le 2026-09-17

`https://staging.motocomparo.com` sert la **v2** depuis le VPS Hostinger
(`<ip-vps>`). Le staging WordPress n'est pas supprimé : pour revenir en
arrière, il suffit de reposer l'enregistrement DNS d'origine.

| | avant | après |
|---|---|---|
| DNS `staging` | ALIAS → `staging.motocomparo.com.cdn.hstgr.net`, TTL 300 | **A → `<ip-vps>`, TTL 300** |

Hostinger refuse un ALIAS et un A sur le même nom : il faut supprimer l'ALIAS
*avant* de créer le A. TTL volontairement court, pour que le retour en arrière
prenne cinq minutes et non quatre heures.

### Ce que le premier déploiement a révélé

- **Les dépendances du site n'étaient déclarées nulle part.** `pip install -e .`
  sur un serveur neuf donnait un environnement sans `fastapi`, `uvicorn`,
  `jinja2` ni `psycopg-pool` : systemd bouclait sur `203/EXEC`. Corrigé dans
  `pyproject.toml`.
- **La clé de cache nginx ignorait le nom d'hôte.** Par défaut elle contient
  `$proxy_host`, soit `127.0.0.1:8000` pour tout le monde : les pages que
  j'avais demandées par l'adresse IP étaient resservies aux visiteurs du nom de
  domaine, plan du site compris. Corrigé en `"$scheme$host$request_uri"`.
- **Un `add_header` dans un bloc enfant efface ceux du parent.** L'interdiction
  d'indexation, posée une seule fois au niveau du serveur, ne sortait sur
  aucune page. Elle est maintenant répétée dans chaque bloc.
- **Le staging est fermé aux moteurs** (`X-Robots-Tag: noindex, nofollow`, sur
  toutes les pages, le plan du site et les fichiers). Sans cela il aurait
  concurrencé la production sur ses propres pages. En production, lancer
  `06-nginx-tls.sh` **sans** `NOINDEX=1`.

### Mesures à la mise en ligne

Base restaurée : 1 498 Mo (313 435 fiches, 763 908 offres vivantes). Le
transfert n'emporte pas `stg_feed_row` ni `offer_signature_bak` — 152 Mo
compressés au lieu de 6,6 Go.

Temps de réponse en HTTPS, VPS à 1 cœur : accueil 0,10 s, bons plans 0,08 s,
rayon casques 0,06 s, fiche produit 0,06 s. Le cache répond `HIT` dès le second
appel.

### Ce qui reste

`07-planification.sh` — le relevé quotidien — n'est pas lancé : il demande les
adresses des flux marchands dans `/srv/motocomparo/.env`. Tant qu'il ne tourne
pas, le catalogue du VPS reste figé au 17/09.
