#!/usr/bin/env bash
# Prépare un VPS Ubuntu 24.04 nu pour motocomparo v2.
#
#     scp ops/vps_install.sh root@<ip>:/root/
#     ssh root@<ip> 'bash /root/vps_install.sh'
#
# Écrit comme un script et non comme une suite de commandes tapées à la main,
# pour trois raisons : on peut le relire avant de l'exécuter sur une machine
# qu'on ne voit pas, on peut le rejouer à l'identique le jour où le serveur est
# recréé, et il est versionné avec le reste du projet.
#
# Idempotent : chaque étape vérifie avant d'agir, donc le relancer ne casse rien.

set -euo pipefail

PG_VERSION=18
APP_USER=mcpipe
APP_DIR=/opt/motocomparo
DB_NAME=mcpipe

echo "=== 1/7  paquets système ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    ca-certificates curl gnupg lsb-release \
    git build-essential \
    python3 python3-venv python3-dev \
    ufw

echo "=== 2/7  pare-feu ==="
# L'ordre compte : on autorise SSH AVANT d'activer le pare-feu, sinon on se
# coupe l'accès à une machine qu'on ne peut atteindre que par SSH.
ufw allow 22/tcp    >/dev/null
ufw allow 80/tcp    >/dev/null
ufw allow 443/tcp   >/dev/null
ufw --force enable  >/dev/null
ufw status numbered | head -8

echo "=== 3/7  PostgreSQL ${PG_VERSION} (dépôt officiel PGDG) ==="
# Ubuntu 24.04 livre PostgreSQL 16 ; le projet est écrit pour 18 et le dépôt
# officiel du projet PostgreSQL est la seule source qui le fournisse.
if [ ! -f /etc/apt/sources.list.d/pgdg.list ]; then
    install -d /usr/share/postgresql-common/pgdg
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list
    apt-get update -qq
fi
apt-get install -y -qq "postgresql-${PG_VERSION}" "postgresql-client-${PG_VERSION}"

echo "=== 4/7  réglages PostgreSQL ==="
# Valeurs pour un traitement par lots sur une petite machine, pas pour un
# serveur web : peu de connexions, de gros regroupements. Mesuré sur le poste de
# développement : `work_mem` par défaut (4 Mo) fait déborder sur disque les
# GROUP BY de `match` sur 763 000 offres.
CONF="/etc/postgresql/${PG_VERSION}/main/conf.d/motocomparo.conf"
install -d "$(dirname "$CONF")"
TOTAL_MB=$(free -m | awk '/Mem:/ {print $2}')
cat > "$CONF" <<EOF
# écrit par ops/vps_install.sh — ne pas éditer à la main
shared_buffers = $((TOTAL_MB / 4))MB
work_mem = 96MB
maintenance_work_mem = $((TOTAL_MB / 8))MB
effective_cache_size = $((TOTAL_MB / 2))MB
max_connections = 40
random_page_cost = 1.1          # disque SSD
EOF
systemctl restart "postgresql@${PG_VERSION}-main"
echo "   shared_buffers=$((TOTAL_MB / 4))MB  work_mem=96MB  (RAM totale ${TOTAL_MB}MB)"

echo "=== 5/7  utilisateur applicatif ==="
# Le pipeline et le site ne tournent pas en root : une faille dans le site ne
# doit pas donner la machine entière.
if ! id "$APP_USER" >/dev/null 2>&1; then
    adduser --system --group --home "$APP_DIR" --shell /bin/bash "$APP_USER"
fi
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR" "$APP_DIR/feeds"

echo "=== 6/7  base de données ==="
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${APP_USER}'" | grep -q 1; then
    sudo -u postgres createuser "$APP_USER"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
    sudo -u postgres createdb -O "$APP_USER" "$DB_NAME"
fi
sudo -u postgres psql -tAc "SELECT version()" | head -1

echo "=== 7/7  vérifications ==="
python3 --version
sudo -u postgres psql -d "$DB_NAME" -tAc "SHOW work_mem"
df -h / | tail -1
echo
echo "PRÊT. Base '${DB_NAME}', utilisateur '${APP_USER}', dossier ${APP_DIR}."
echo "Rien n'écoute encore sur le port 80 : le site n'est pas déployé."
