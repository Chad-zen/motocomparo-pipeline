#!/usr/bin/env bash
# 03 — Le code et son environnement Python.
#
#   bash 03-application.sh
#
# Le dépôt est PUBLIC et volontairement anonymisé : rien de secret n'y est, donc
# un simple `git clone` suffit. Les secrets (base, mots de passe des flux) vivent
# dans `/srv/motocomparo/.env`, qui n'est jamais commité.
set -euo pipefail

DEPOT="${DEPOT:-}"
if [ -z "$DEPOT" ]; then
    echo "Indiquer l'adresse du dépôt :"
    echo "   DEPOT=https://github.com/…/motocomparo-pipeline.git bash 03-application.sh"
    exit 1
fi

cd /srv/motocomparo
if [ -d app/.git ]; then
    echo "== mise à jour du code =="
    sudo -u motocomparo git -C app pull --ff-only
else
    echo "== récupération du code =="
    sudo -u motocomparo git clone --depth 1 "$DEPOT" app
fi

echo "== environnement Python =="
# `--upgrade-strategy only-if-needed` : on ne met à jour une dépendance que si
# le projet l'exige. Un environnement qui dérive tout seul finit par ne plus
# ressembler à celui où les 159 tests passent.
sudo -u motocomparo python3 -m venv /srv/motocomparo/venv
sudo -u motocomparo /srv/motocomparo/venv/bin/pip install --quiet --upgrade pip
sudo -u motocomparo /srv/motocomparo/venv/bin/pip install --quiet -e /srv/motocomparo/app

echo "== fichier d'environnement =="
if [ ! -f /srv/motocomparo/.env ]; then
    cp /srv/motocomparo/.env.base /srv/motocomparo/.env
    cat >> /srv/motocomparo/.env <<'ENVFILE'

# --- les flux marchands -------------------------------------------------
# À RECOPIER depuis le .env du poste de développement. Ces adresses contiennent
# des jetons d'affiliation : elles ne sont dans aucun dépôt, et ne doivent pas
# l'être.
# FEED_SPEEDWAY_URL=
# FEED_LABECANERIE_URL=
# FEED_MOTOBLOUZ_URL=
# FEED_MAXXESS_URL=
# FEED_MOTOAXXE_URL=
# FEED_FCMOTO_URL=

# --- le site ------------------------------------------------------------
# Durée du cache applicatif, en secondes. Les prix changent une fois par jour :
# dix minutes est prudent, et le cache est vidé à la fin du relevé quotidien.
SITE_CACHE_TTL=600

# Les mentions légales. Éditeur et directeur de la publication ne s'affichent
# QUE s'ils sont renseignés : une mention à moitié remplie vaut moins qu'une
# ligne absente. À recopier depuis le .env du poste — ils portent un nom réel,
# c'est pourquoi ils ne sont pas écrits ici : ce fichier est dans un dépôt
# public.
# MENTIONS_EDITEUR=
# MENTIONS_DIRECTEUR=
# L'adresse de contact, elle, a déjà sa valeur par défaut dans le code
# (contact@motocomparo.com). Ne la décommenter que pour en changer.
# MENTIONS_CONTACT=
ENVFILE
    chown motocomparo:motocomparo /srv/motocomparo/.env
    chmod 600 /srv/motocomparo/.env
    echo "   /srv/motocomparo/.env créé — À COMPLÉTER avec les adresses des flux"
else
    echo "   /srv/motocomparo/.env existe déjà, laissé tel quel"
fi

echo "== schéma de la base =="
for f in /srv/motocomparo/app/sql/*.sql; do
    echo "   $(basename "$f")"
    sudo -u motocomparo env $(grep -h '^DATABASE_URL' /srv/motocomparo/.env) \
        psql "$DATABASE_URL" -q -v ON_ERROR_STOP=1 -f "$f" 2>/dev/null \
      || sudo -u postgres psql -d mcpipe -q -v ON_ERROR_STOP=1 -f "$f"
done

echo
echo "OK. Étape suivante : le transfert de la base (04-transfert-base.md),"
echo "    OU directement 05-service.sh si tu repars d'une base vide."
