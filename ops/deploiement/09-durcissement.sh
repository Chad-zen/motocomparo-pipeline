#!/usr/bin/env bash
# 09 — Ce que l'audit du 30/09/2026 a trouvé ouvert sur le serveur.
#
#   bash 09-durcissement.sh
#
# Rejouable : chaque étape écrit un fichier entier ou teste avant d'agir.
#
#   1. nginx : version masquée, /admin et /contact hors cache, débit du
#      formulaire limité, robot d'entraînement de Meta refusé, gzip niveau 6 ;
#   2. SSH : plus de mot de passe (la clé seule), root par clé seulement,
#      fail2ban sur le port 22 ;
#   3. sauvegarde quotidienne de la base, 5 jours gardés sur le VPS.
#
# ⚠ SSH : garder une session ouverte pendant le rechargement, et vérifier
# qu'une NOUVELLE connexion par clé passe avant de la fermer.
set -euo pipefail
ICI="$(cd "$(dirname "$0")" && pwd)"

echo "== 1. nginx =="
install -m 644 "$ICI/nginx/motocomparo-http.conf" /etc/nginx/conf.d/motocomparo-http.conf
install -d /etc/nginx/snippets
install -m 644 "$ICI/nginx/motocomparo-server.conf" /etc/nginx/snippets/motocomparo-server.conf
# Inclus UNE fois, juste après error_log, dans le bloc qui sert les pages
# (celui que certbot a complété de ses lignes 443 : on n'y touche pas).
if ! grep -q 'snippets/motocomparo-server.conf' /etc/nginx/sites-available/motocomparo; then
    sed -i '0,/error_log .*motocomparo.error.log;/s//&\n    include \/etc\/nginx\/snippets\/motocomparo-server.conf;/' \
        /etc/nginx/sites-available/motocomparo
fi
nginx -t
systemctl reload nginx
# une page /admin déjà en cache y resterait une heure
find /var/cache/nginx/motocomparo -type f -delete

echo "== 2. SSH =="
# cloud-init pose PasswordAuthentication yes dans 50-cloud-init.conf, qui
# l'emporte sur tout ce qui suit (le premier réglage lu gagne chez sshd).
cat > /etc/ssh/sshd_config.d/10-motocomparo.conf <<'SSHD'
# Audit du 30/09/2026 : connexion par clé uniquement.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
X11Forwarding no
SSHD
sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' \
    /etc/ssh/sshd_config.d/50-cloud-init.conf 2>/dev/null || true
sshd -t
systemctl reload ssh

if ! command -v fail2ban-client >/dev/null; then
    apt-get install -y fail2ban
fi
cat > /etc/fail2ban/jail.d/motocomparo.local <<'JAIL'
[sshd]
enabled  = true
backend  = systemd
# Sous Ubuntu le service s'appelle ssh.service : le filtre par defaut vise
# sshd.service et ne voyait donc AUCUNE tentative (verifie le 30/09/2026).
journalmatch = _COMM=sshd
maxretry = 5
findtime = 10m
bantime  = 1h
JAIL
systemctl enable --now fail2ban
systemctl restart fail2ban

echo "== 2 bis. cache réchauffé au démarrage du site =="
install -m 755 "$ICI/rechauffer.sh" /usr/local/bin/mcsite-rechauffer
install -d /etc/systemd/system/mcsite.service.d
cat > /etc/systemd/system/mcsite.service.d/rechauffer.conf <<'UNIT'
[Service]
# le « - » : un réchauffage raté ne doit jamais faire échouer le démarrage
ExecStartPost=-/usr/local/bin/mcsite-rechauffer
UNIT
systemctl daemon-reload

echo "== 3. sauvegarde de la base =="
install -d -o mcpipe -g mcpipe -m 700 /srv/motocomparo/sauvegardes
cat > /usr/local/bin/mcpipe-sauvegarde <<'SCRIPT'
#!/usr/bin/env bash
# pg_dump compressé, un fichier par jour, 5 jours gardés. La base fait 6 Go ;
# le disque en a 48. Une copie HORS du VPS reste à brancher.
set -euo pipefail
cd /srv/motocomparo/sauvegardes
f="mcpipe-$(date +%F).dump"
pg_dump -Fc -d mcpipe -f "$f.part"
mv "$f.part" "$f"
chmod 600 "$f"
ls -1t mcpipe-*.dump | tail -n +6 | xargs -r rm -f
ls -lh "$f"
SCRIPT
chmod +x /usr/local/bin/mcpipe-sauvegarde

cat > /etc/systemd/system/mcpipe-sauvegarde.service <<'UNIT'
[Unit]
Description=MotoComparo — sauvegarde quotidienne de la base
After=postgresql@18-main.service

[Service]
Type=oneshot
User=mcpipe
Group=mcpipe
ExecStart=/usr/local/bin/mcpipe-sauvegarde
Nice=15
IOSchedulingClass=idle
UNIT

cat > /etc/systemd/system/mcpipe-sauvegarde.timer <<'UNIT'
[Unit]
Description=MotoComparo — sauvegarde quotidienne de la base

[Timer]
# 3 h : avant le relevé de prix de 4 h, la base est au repos.
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now mcpipe-sauvegarde.timer
systemctl list-timers mcpipe-sauvegarde.timer --no-pager

echo
echo "OK. Restaurer :  pg_restore -d <base_vide> /srv/motocomparo/sauvegardes/mcpipe-<date>.dump"
