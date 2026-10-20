#!/usr/bin/env bash
# 12 - Motoin dans la chaine de nuit : l URL de son flux, et rien d autre.
#
#   FEED_MOTOIN_URL='https://platform-api.webgains.com/...' bash 12-motoin.sh
#     (ou : la ligne FEED_MOTOIN_URL=... sur l'entree standard)
#
# L URL (du flux Webgains, a ne jamais ecrire dans le depot) vit dans `/srv/motocomparo/motoin.env`, root, 0600, et
# n'entre dans l'environnement que du service `mcpipe-prix`, par un drop-in systemd. Elle n'est
# PAS dans `/srv/motocomparo/.env` : `configured_feeds()` retourne tout flux dont l'URL est dans
# l'environnement, donc un `mcpipe fetch` lance a la main sans `--only` le telechargerait.
# systemd lit un EnvironmentFile en root AVANT de laisser tomber les droits (`User=motocomparo`) :
# le fichier n'a pas besoin d'etre lisible par le compte applicatif.
#
# Ce script ne touche pas a `mcpipe-prix` lui-meme (voir 07-planification.sh : liste NEUFS).
set -euo pipefail

fichier=/srv/motocomparo/motoin.env
if [ -n "${FEED_MOTOIN_URL:-}" ]; then
  ligne="FEED_MOTOIN_URL=${FEED_MOTOIN_URL}"
elif [ ! -t 0 ]; then
  ligne="$(cat)"
else
  echo "donner FEED_MOTOIN_URL en variable ou sur l'entree standard" >&2; exit 1
fi
case "$ligne" in FEED_MOTOIN_URL=http*) ;; *) echo "ligne inattendue (attendu FEED_MOTOIN_URL=http...)" >&2; exit 1;; esac

umask 077
printf '%s\n' "$ligne" > "$fichier"
chown root:root "$fichier"; chmod 600 "$fichier"

mkdir -p /etc/systemd/system/mcpipe-prix.service.d
cat > /etc/systemd/system/mcpipe-prix.service.d/motoin.conf <<'CONF'
[Service]
EnvironmentFile=/srv/motocomparo/motoin.env
CONF
systemctl daemon-reload
systemctl show mcpipe-prix.service -p EnvironmentFiles | sed 's/=.*motoin.env.*/ ... motoin.env present/;t;s/.*/EnvironmentFiles : motoin.env ABSENT/'
echo "ok : la chaine de nuit lira la URL de Motoin"
