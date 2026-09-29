#!/usr/bin/env bash
# 08 — Le relevé quotidien des codes promo, oublié à l'installation.
#
#   bash 08-planification-promo.sh
#
# `mcpipe promo` existait depuis le début (voir `src/mcpipe/promo.py`), avec sa
# propre doc qui dit noir sur blanc qu'il tourne « sur son propre calendrier,
# indépendant de la chaîne du catalogue ». Ce calendrier n'a jamais été posé :
# seul `07-planification.sh` (les prix) a eu droit à son timer. Le relevé du
# 13-14/09/2026, fait une fois à la main pendant l'installation, est resté seul
# — signalé par la propriétaire le 29/09/2026, deux semaines plus tard, en
# constatant que les codes affichés n'étaient plus ceux des marchands.
set -euo pipefail

cat > /usr/local/bin/mcpipe-promo <<'SCRIPT'
#!/usr/bin/env bash
# Une seule étape, volontairement séparée de `mcpipe-prix` : le relevé promo
# ne touche ni offre ni produit (voir la docstring de `mcpipe promo`), il peut
# donc tourner à une autre heure, sans dépendre de la réussite du relevé de
# prix ni attendre derrière lui sur l'unique cœur du VPS.
set -euo pipefail
export PATH=/srv/motocomparo/venv/bin:$PATH
cd /srv/motocomparo/app

echo "=== $(date '+%F %T') début ==="
mcpipe promo
echo "=== $(date '+%F %T') fin ==="
SCRIPT
chmod +x /usr/local/bin/mcpipe-promo

cat > /etc/systemd/system/mcpipe-promo.service <<'UNIT'
[Unit]
Description=MotoComparo — relevé quotidien des codes promo
After=network-online.target postgresql@18-main.service
Wants=network-online.target

[Service]
Type=oneshot
User=motocomparo
Group=motocomparo
EnvironmentFile=/srv/motocomparo/.env
ExecStart=/usr/local/bin/mcpipe-promo

# Un code retiré ou renouvelé doit se voir sans attendre l'heure de cache
# restante — même geste que `mcpipe-prix.service`, même raison.
ExecStartPost=+/usr/bin/find /var/cache/nginx/motocomparo -type f -delete

# Cinq requêtes HTTP et quelques upserts : rien qui justifie de déranger le
# relevé de prix. Même traitement de politesse envers les visiteurs que lui.
Nice=10
IOSchedulingClass=idle

# Un relevé promo qui dépasse dix minutes est un relevé qui a trouvé un site
# bloqué (La Bécanerie, derrière Cloudflare, en connaît le chemin) : on coupe
# plutôt que de laisser la tâche tourner jusqu'au lendemain.
TimeoutStartSec=10m
UNIT

cat > /etc/systemd/system/mcpipe-promo.timer <<'UNIT'
[Unit]
Description=MotoComparo — relevé quotidien des codes promo

[Timer]
# 6 h du matin : une heure après le relevé de prix (4 h), pour ne jamais
# disputer le même cœur au même instant, et avant les premiers visiteurs.
OnCalendar=*-*-* 06:00:00
Persistent=true
RandomizedDelaySec=15m

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now mcpipe-promo.timer
systemctl list-timers mcpipe-promo.timer --no-pager

echo
echo "Pour l'essayer tout de suite :   systemctl start mcpipe-promo"
echo "Pour lire ce qui s'est passé :   journalctl -u mcpipe-promo -n 60"
