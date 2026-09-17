#!/usr/bin/env bash
# 02 — PostgreSQL, réglé pour 4 Go de mémoire.
#
#   bash 02-postgres.sh
#
# Les valeurs ci-dessous ne sont pas des recettes copiées : elles viennent de la
# taille réelle du catalogue (≈760 000 offres, base de 500 à 600 Mo d'après
# docs/infrastructure.md) et de la mémoire du VPS.
set -euo pipefail

echo "== dépôt officiel PostgreSQL =="
# Celui d'Ubuntu retarde d'une version majeure. On prend le dépôt du projet,
# qui est aussi celui que le poste de développement utilise — deux versions
# différentes entre développement et production, c'est une classe de bugs
# gratuite.
install -d /usr/share/postgresql-common/pgdg
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
     -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
apt-get update -qq
apt-get install -y -qq postgresql-18 postgresql-client-18

CONF=/etc/postgresql/18/main/conf.d/motocomparo.conf
echo "== réglages ($CONF) =="
cat > "$CONF" <<'PGCONF'
# Réglages MotoComparo — VPS 1 vCPU / 4 Go.
#
# shared_buffers : le quart de la mémoire, la règle usuelle. Le catalogue fait
# 500-600 Mo : il tient donc ENTIÈREMENT en cache, et c'est ce qui permet à une
# fiche de sortir sans toucher le disque.
shared_buffers = 1GB

# effective_cache_size ne réserve rien : c'est ce que le planificateur croit
# disponible entre PostgreSQL et le cache du système. Trop bas, il choisit des
# balayages complets là où un index suffisait.
effective_cache_size = 2500MB

# work_mem est PAR TRI et par connexion. Le site en ouvre 6 au maximum
# (`ConnectionPool(max_size=6)` dans app.py), et le pipeline une seule : 32 Mo
# reste très loin de saturer la mémoire, tout en évitant les tris sur disque.
work_mem = 32MB

# maintenance_work_mem sert aux VACUUM, aux index et aux ANALYZE. C'est le seul
# endroit où être généreux ne coûte rien : ces opérations sont ponctuelles.
maintenance_work_mem = 256MB

# Un seul disque NVMe : parcourir un index n'y coûte presque pas plus cher que
# lire séquentiellement. La valeur par défaut (4.0) date des disques à plateaux
# et pousse le planificateur à éviter les index à tort.
random_page_cost = 1.1
effective_io_concurrency = 200

# UN SEUL CŒUR : le parallélisme ne peut rien apporter et ne fait qu'ajouter de
# la synchronisation. On le coupe.
max_parallel_workers_per_gather = 0
max_parallel_workers = 0

# Les statistiques. Trois pannes le 2026-09-14 venaient de statistiques
# périmées après une réécriture massive — dont une passe partie pour des
# dizaines d'heures. On laisse l'autovacuum réagir plus tôt qu'au défaut.
autovacuum_vacuum_scale_factor = 0.05
autovacuum_analyze_scale_factor = 0.02
default_statistics_target = 200

# Toute requête de plus de 2 s est écrite dans le journal. C'est le seul moyen
# de voir venir une lenteur avant que ce soit un visiteur qui la signale.
log_min_duration_statement = 2000

# PostgreSQL n'écoute QUE la boucle locale : le site tourne sur la même machine.
listen_addresses = 'localhost'
PGCONF

systemctl restart postgresql@18-main
systemctl enable postgresql@18-main

echo "== base et utilisateur =="
# Le mot de passe est TIRÉ AU SORT ici et écrit dans le fichier d'environnement
# de l'application. Personne n'a à le choisir, donc personne ne le réutilise
# ailleurs, et il n'apparaît dans aucun historique de commandes.
MDP=$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 24)
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mcpipe') THEN
    CREATE ROLE mcpipe LOGIN PASSWORD '${MDP}';
  ELSE
    ALTER ROLE mcpipe PASSWORD '${MDP}';
  END IF;
END \$\$;
SQL
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='mcpipe'" \
  | grep -q 1 || sudo -u postgres createdb -O mcpipe mcpipe

install -d -o motocomparo -g motocomparo /srv/motocomparo
umask 077
printf 'DATABASE_URL=postgresql://mcpipe:%s@localhost:5432/mcpipe\n' "$MDP" \
    > /srv/motocomparo/.env.base
chown motocomparo:motocomparo /srv/motocomparo/.env.base
chmod 600 /srv/motocomparo/.env.base

echo "   base « mcpipe » prête, identifiants dans /srv/motocomparo/.env.base"
echo
echo "OK. Étape suivante : bash 03-application.sh"
