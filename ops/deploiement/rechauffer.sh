#!/usr/bin/env bash
# Réchauffe le cache du site juste après un démarrage de mcsite.
#
# Audit du 30/09/2026 : après chaque redémarrage, le premier visiteur de
# /produits attendait 39 s (et nginx rendait un 504 à 60 s), /c/boots 17 s —
# le temps de recalculer listes et facettes que le cache applicatif garde
# ensuite dix minutes. Ce script les demande lui-même, une par une, avant
# qu'un visiteur ne le fasse.
#
# Lancé par ExecStartPost du service (drop-in posé par 09-durcissement.sh) :
# il se détache aussitôt pour ne pas retarder le démarrage.
set -u
if [ "${1:-}" != "--detache" ]; then
    setsid "$0" --detache >/dev/null 2>&1 < /dev/null &
    exit 0
fi

B=http://127.0.0.1:8000
for i in $(seq 1 30); do
    curl -s -o /dev/null --max-time 5 "$B/robots.txt" && break
    sleep 2
done
# séquentiel exprès : une seule requête lourde à la fois sur le cœur unique
pages="/ /produits /bons-plans /marques"
rayons=$(curl -s --max-time 120 "$B/" | grep -o 'href="/c/[a-z_]*"' | sort -u | cut -d'"' -f2)
for u in $pages $rayons; do
    curl -s -o /dev/null --max-time 120 "$B$u"
done
