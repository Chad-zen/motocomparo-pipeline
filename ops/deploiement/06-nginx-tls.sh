#!/usr/bin/env bash
# 06 — La façade : nginx, le CACHE, puis HTTPS.
#
#   DOMAINE=staging.motocomparo.com bash 06-nginx-tls.sh
#
# C'est l'étape qui décide de la vitesse du site. Le reste est de la plomberie.
set -euo pipefail

DOMAINE="${DOMAINE:-}"
[ -z "$DOMAINE" ] && { echo "DOMAINE=staging.motocomparo.com bash 06-nginx-tls.sh"; exit 1; }

install -d -o www-data -g www-data /var/cache/nginx/motocomparo

cat > /etc/nginx/conf.d/motocomparo-cache.conf <<'CACHECONF'
# Le cache de pages.
#
# Mesuré le 2026-09-14 : sans cache, l'accueil mettait 12 s, la recherche 16 s,
# les bons plans 17 s — sur une machine à 12 cœurs. Le VPS en a UN. Servir des
# pages déjà fabriquées n'est donc pas une optimisation, c'est la condition pour
# que le site tienne debout.
#
# keys_zone=10m : environ 80 000 pages référencées, largement au-delà du besoin.
# max_size=1g   : le disque fait 50 Go, on en prend 1.
# inactive=24h  : une fiche que personne n'ouvre de la journée sort du cache.
proxy_cache_path /var/cache/nginx/motocomparo levels=1:2
                 keys_zone=mc:10m max_size=1g inactive=24h use_temp_path=off;
CACHECONF

cat > /etc/nginx/sites-available/motocomparo <<CONF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAINE};

    # Les pages sont déjà compressées par nginx ; les images viennent des
    # marchands et ne passent pas par ici.
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;

    access_log /var/log/nginx/motocomparo.access.log;
    error_log  /var/log/nginx/motocomparo.error.log;

    # Les fichiers du site (CSS, logo, la bibliothèque du graphique) ne changent
    # que lorsque leur adresse change — elle porte un numéro de version. On peut
    # donc dire aux navigateurs de les garder un an.
    location /static/ {
        alias /srv/motocomparo/app/src/mcsite/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_cache mc;
        # Une heure. Les prix sont relevés une fois par jour : une page d'une
        # heure ne ment pas. Le cache est de toute façon vidé à la fin du relevé
        # quotidien (voir 07-planification.sh), donc un prix neuf est visible
        # tout de suite après la collecte.
        proxy_cache_valid 200 301 302 1h;
        proxy_cache_valid 404 1m;

        # DEUX réglages qui font tout le travail sur une machine à un cœur :
        #
        # proxy_cache_use_stale : si l'application est occupée, en erreur, ou
        #   en train de redémarrer, on continue de servir la version en cache.
        #   Un visiteur ne voit jamais une page blanche pendant que le pipeline
        #   tourne.
        # proxy_cache_background_update : la page périmée est servie
        #   IMMÉDIATEMENT et rafraîchie derrière. Personne n'attend jamais la
        #   reconstruction.
        #
        # Aucun accent grave dans ce bloc : il est volontairement NON protégé,
        # pour que le nom de domaine soit remplacé, et bash y prendrait un
        # accent grave pour une commande à exécuter. C'est arrivé au premier
        # déploiement, le 2026-09-17.
        proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
        proxy_cache_background_update on;

        # Cent visiteurs qui arrivent en même temps sur une page absente du
        # cache : un seul la demande à l'application, les autres attendent son
        # résultat. Sans ça, un cœur unique reçoit cent fois la même requête.
        proxy_cache_lock on;
        proxy_cache_lock_timeout 20s;

        # Pour voir, dans le navigateur, si la page vient du cache : HIT, MISS,
        # UPDATING, STALE. C'est le seul moyen de vérifier que tout ceci sert.
        add_header X-Cache \$upstream_cache_status;

        proxy_read_timeout 60s;
    }
}
CONF

ln -sf /etc/nginx/sites-available/motocomparo /etc/nginx/sites-enabled/motocomparo
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo
echo "== certificat HTTPS =="
echo "   ⚠ Le DNS de ${DOMAINE} doit DÉJÀ pointer sur ce VPS, sinon certbot"
echo "     échoue et il faudra recommencer. Vérifier d'abord :"
echo "        dig +short ${DOMAINE}"
echo
read -r -p "   Le DNS est-il basculé ? [o/N] " reponse
if [ "$reponse" = "o" ] || [ "$reponse" = "O" ]; then
    certbot --nginx -d "${DOMAINE}" --redirect --agree-tos --no-eff-email
    systemctl reload nginx
    echo "   certificat en place, renouvellement automatique actif"
else
    echo "   certificat reporté. Relancer plus tard :"
    echo "        certbot --nginx -d ${DOMAINE} --redirect"
fi

echo
echo "OK. Étape suivante : bash 07-planification.sh"
