#!/usr/bin/env bash
# 01 — Le système : paquets, utilisateur applicatif, pare-feu.
#
# À lancer en root sur le VPS, une seule fois.
#   bash 01-systeme.sh
#
# Ce script ne touche à aucune donnée : il installe et il ferme des portes.
set -euo pipefail

echo "== mise à jour des paquets =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

echo "== paquets nécessaires =="
# `python3-venv` : l'application vit dans son propre environnement, jamais dans
#   le Python du système — une mise à jour d'Ubuntu ne doit pas casser le site.
# `nginx` : la façade et le cache (voir README pour le choix).
# `certbot` : le certificat HTTPS, renouvelé tout seul.
# `unattended-upgrades` : les correctifs de sécurité s'appliquent sans nous.
apt-get install -y -qq \
    python3 python3-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    git curl ca-certificates \
    ufw unattended-upgrades

echo "== utilisateur applicatif =="
# Le site ne tourne PAS en root. Si une faille est trouvée dans l'application,
# elle est trouvée dans un compte qui ne peut rien faire d'autre que lire ses
# propres fichiers.
if ! id -u motocomparo >/dev/null 2>&1; then
    adduser --system --group --home /srv/motocomparo --shell /usr/sbin/nologin motocomparo
    echo "   utilisateur motocomparo créé"
else
    echo "   utilisateur motocomparo déjà présent"
fi
install -d -o motocomparo -g motocomparo /srv/motocomparo

echo "== pare-feu =="
# On ouvre trois portes et on ferme tout le reste. PostgreSQL n'écoute que sur
# la boucle locale (voir 02) : il n'a aucune raison d'être joignable de
# l'extérieur, et c'est la première chose qu'un scanner essaie.
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
ufw status verbose

echo "== correctifs de sécurité automatiques =="
dpkg-reconfigure -f noninteractive unattended-upgrades

echo
echo "OK. Étape suivante : bash 02-postgres.sh"
