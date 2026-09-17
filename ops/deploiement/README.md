# Déployer la v2 sur le VPS

Ce dossier contient tout ce qu'il faut pour mettre MotoComparo v2 en ligne, dans
l'ordre. **Aucun script ne s'exécute tout seul** : on les lance un par un et on
regarde ce qui se passe entre chacun.

Cible : le VPS Hostinger KVM 1 (`<hote-vps>`, Ubuntu 24.04),
provisionné le 2026-09-13. Le sous-domaine `staging.motocomparo.com` sera
basculé du mutualisé vers lui — la production WordPress et le staging WordPress
ne sont **pas** touchés tant que la v2 n'a pas fait ses preuves.

## L'ordre

| | quoi | durée | site en ligne ? |
|---|---|---|---|
| 1 | `01-systeme.sh` — paquets, utilisateur, pare-feu | 5 min | — |
| 2 | `02-postgres.sh` — PostgreSQL + réglages 4 Go | 5 min | — |
| 3 | `03-application.sh` — code, environnement Python | 5 min | — |
| 4 | `04-transfert-base.md` — la base, depuis le PC | 30-60 min | — |
| 5 | `05-service.sh` — le service qui tient le site debout | 2 min | oui, en HTTP |
| 6 | `06-nginx-tls.sh` — le serveur de façade, le cache, HTTPS | 10 min | oui, en HTTPS |
| 7 | `07-planification.sh` — le relevé de prix quotidien | 5 min | — |

## Les trois décisions, et pourquoi

### nginx plutôt que Caddy

Caddy est plus simple et obtient son certificat tout seul. On prend quand même
nginx, pour une raison mesurée : **le cache est le sujet principal de ce site**,
pas le TLS.

Mesuré le 2026-09-14 sur le PC de développement : sans cache, la page d'accueil
mettait 12 s, la recherche 16 s, les bons plans 17 s. Avec le cache applicatif,
les bons plans sont passés à 0,02 s. Le VPS est un **1 vCPU** — soit bien moins
que la machine où ces chiffres ont été relevés. Servir des pages déjà prêtes est
donc la seule façon de tenir.

`proxy_cache` est natif chez nginx. Chez Caddy il demande un module tiers et une
recompilation. Le certificat, lui, s'obtient en une commande avec certbot.

### Les prix changent une fois par jour

C'est ce qui rend le cache honnête : une fiche peut rester en cache des heures
sans mentir. Le cache est purgé à la fin du relevé quotidien, pas avant.

### Le pipeline et le site sur la même machine

Sur 1 vCPU, ils se disputent le processeur. Deux garde-fous :

- le relevé quotidien tourne **la nuit** (timer systemd à 4 h) ;
- pendant qu'il tourne, le cache continue de servir les visiteurs.

Le `match` complet, lui, reste une opération manuelle et exceptionnelle : il
dure 45 minutes et demande l'arrêt du site. Il ne fait pas partie du quotidien.

## Ce que je ne peux pas faire à ta place

- **La connexion SSH.** Je ne saisis pas d'identifiants. C'est toi qui ouvres la
  session ; ensuite je peux te dicter ou te préparer chaque commande.
- **Le changement DNS** de `staging.motocomparo.com` vers l'IP du VPS, dans
  hPanel.
- **L'IP du VPS** : elle n'est pas encore notée dans `docs/infrastructure.md`.

## Le retour en arrière

À chaque étape, rien n'est détruit côté WordPress. Si la v2 ne tient pas :
remettre l'enregistrement DNS de `staging` sur le mutualisé, et le staging
WordPress réapparaît tel qu'il était. C'est pour ça qu'on ne le supprime pas
maintenant.

## Après le déploiement — les trois vérifications

``bash
# 1. Le site répond, et le cache fonctionne.
curl -sI https://staging.motocomparo.com/ | grep -i x-cache   # MISS
curl -sI https://staging.motocomparo.com/ | grep -i x-cache   # HIT

# 2. Les temps de réponse, page froide puis page chaude.
for u in / /bons-plans /marques; do
  curl -so /dev/null -w "$u  %{time_total}s\n" https://staging.motocomparo.com$u
done

# 3. Le relevé de nuit est bien programmé.
systemctl list-timers mcpipe-prix.timer
``

Le second appel doit être **très** inférieur au premier. S'ils sont identiques,
le cache ne fonctionne pas : vérifier que l'application n'envoie pas d'en-tête
`Cache-Control: no-store`.
