#!/usr/bin/env bash
# 11 — Motard Bleu dans la chaine de nuit : la cle de son flux, et rien d'autre.
#
#   FEED_MOTARDBLEU_URL='https://productdata.awin.com/...' bash 11-motardbleu.sh
#     (ou : la ligne FEED_MOTARDBLEU_URL=... sur l'entree standard)
#
# La cle (dans l'URL du flux Awin) vit dans `/srv/motocomparo/motardbleu.env`, root, 0600, et
# n'entre dans l'environnement que du service `mcpipe-prix`, par un drop-in systemd. Elle n'est
# PAS dans `/srv/motocomparo/.env` : `configured_feeds()` retourne tout flux dont l'URL est dans
# l'environnement, donc un `mcpipe fetch` lance a la main sans `--only` le telechargerait.
# systemd lit un EnvironmentFile en root AVANT de laisser tomber les droits (`User=motocomparo`) :
# le fichier n'a pas besoin d'etre lisible par le compte applicatif.
#
# Ce script ne touche pas a `mcpipe-prix` lui-meme (voir 07-planification.sh : liste NEUFS).
set -euo pipefail

fichier=/srv/motocomparo/motardbleu.env
if [ -n "${FEED_MOTARDBLEU_URL:-}" ]; then
  ligne="FEED_MOTARDBLEU_URL=${FEED_MOTARDBLEU_URL}"
elif [ ! -t 0 ]; then
  ligne="$(cat)"
else
  echo "donner FEED_MOTARDBLEU_URL en variable ou sur l'entree standard" >&2; exit 1
fi
case "$ligne" in FEED_MOTARDBLEU_URL=http*) ;; *) echo "ligne inattendue (attendu FEED_MOTARDBLEU_URL=http...)" >&2; exit 1;; esac

umask 077
printf '%s\n' "$ligne" > "$fichier"
chown root:root "$fichier"; chmod 600 "$fichier"

mkdir -p /etc/systemd/system/mcpipe-prix.service.d
cat > /etc/systemd/system/mcpipe-prix.service.d/motardbleu.conf <<'CONF'
[Service]
EnvironmentFile=/srv/motocomparo/motardbleu.env
CONF
systemctl daemon-reload
systemctl show mcpipe-prix.service -p EnvironmentFiles | sed 's/=.*motardbleu.env.*/ ... motardbleu.env present/;t;s/.*/EnvironmentFiles : motardbleu.env ABSENT/'
echo "ok : la chaine de nuit lira la cle de Motard Bleu"
