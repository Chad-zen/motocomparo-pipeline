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

echo "== fichier d'échange =="
# Le VPS n'en a aucun par défaut. Sur une machine à UN cœur et 3,8 Go, l'absence
# de swap ne rend rien plus rapide : elle transforme un pic de mémoire passager
# — une restauration de base, un `match`, un VACUUM — en processus tué net.
# Deux gigaoctets ne servent jamais en régime normal ; ils servent le jour où
# ça déborde, et ce jour-là ils évitent de tout relancer.
if ! swapon --show | grep -q .; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    # 10 : on ne s'en sert qu'en dernier recours. Le défaut (60) ferait sortir
    # des pages encore utiles vers le disque sans raison.
    sysctl -q -w vm.swappiness=10
    grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
    echo "   2 Go d'échange en place"
else
    echo "   échange déjà configuré"
fi

echo "== correctifs de sécurité automatiques =="
dpkg-reconfigure -f noninteractive unattended-upgrades

echo
echo "OK. Étape suivante : bash 02-postgres.sh"
