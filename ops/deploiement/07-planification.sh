#!/usr/bin/env bash
# 07 — Le relevé de prix quotidien, et le vidage du cache derrière.
#
#   bash 07-planification.sh
#
# Le site promet en bas de chaque page que « les prix sont relevés chaque jour ».
# Sur le poste de développement, rien ne l'exécutait : il fallait qu'une
# personne lance la chaîne à la main. Ici, c'est systemd qui s'en charge.
set -euo pipefail

cat > /usr/local/bin/mcpipe-prix <<'SCRIPT'
#!/usr/bin/env bash
# La chaîne quotidienne. `match` n'en fait PAS partie, à dessein : il dure
# 45 minutes, demande l'arrêt du site, et ne sert que lorsqu'une règle de
# rapprochement change. Sans lui, les prix des fiches existantes sont à jour —
# c'est exactement ce que la phrase du site promet.
set -euo pipefail
export PATH=/srv/motocomparo/venv/bin:$PATH
cd /srv/motocomparo/app
set -a; . /srv/motocomparo/.env; set +a

echo "=== $(date '+%F %T') début ==="

# `fetch` ne retélécharge que ce qui a changé : il joint l'empreinte de la copie
# qu'on a déjà, et cinq marchands sur six répondent « rien de neuf » sans
# envoyer un octet. Mesuré le 2026-09-14 : 926 Mo → 270 Mo.
mcpipe fetch
mcpipe load
mcpipe normalize
mcpipe signature      # porte les tailles ; doit précéder enrich
mcpipe enrich         # catégories + emprunt des tailles au code-barres
mcpipe freshness      # recalcule les prix affichés — jamais optionnel

# Le cache de nginx garde les pages une heure. Après une collecte, elles sont
# périmées : on les jette, sinon les nouveaux prix attendent jusqu'à une heure
# pour apparaître.
find /var/cache/nginx/motocomparo -type f -delete 2>/dev/null || true
echo "   cache de pages vidé"

echo "=== $(date '+%F %T') fin ==="
SCRIPT
chmod +x /usr/local/bin/mcpipe-prix

cat > /etc/systemd/system/mcpipe-prix.service <<'UNIT'
[Unit]
Description=MotoComparo — relevé quotidien des prix
After=network-online.target postgresql@18-main.service
Wants=network-online.target

[Service]
Type=oneshot
User=motocomparo
Group=motocomparo
ExecStart=/usr/local/bin/mcpipe-prix

# Le VPS a UN cœur, partagé avec le site. On met le pipeline derrière les
# visiteurs : il ira un peu moins vite, personne ne verra la différence, et une
# page ne restera pas bloquée derrière un téléchargement de 270 Mo.
Nice=10
IOSchedulingClass=idle

# Une chaîne qui dépasse trois heures est une chaîne en panne. On la coupe
# plutôt que de la laisser tenir la machine jusqu'au lendemain.
TimeoutStartSec=3h
UNIT

cat > /etc/systemd/system/mcpipe-prix.timer <<'UNIT'
[Unit]
Description=MotoComparo — relevé quotidien des prix

[Timer]
# 4 h du matin : personne ne lit un comparateur d'équipement moto à cette
# heure-là, et les marchands ont republié leurs flux pendant la nuit.
OnCalendar=*-*-* 04:00:00
# Si le VPS était éteint à 4 h, on rattrape au démarrage plutôt que de sauter
# une journée — une journée sautée, c'est un prix vieux de 48 h affiché comme
# s'il datait d'hier.
Persistent=true
RandomizedDelaySec=15m

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now mcpipe-prix.timer
systemctl list-timers mcpipe-prix.timer --no-pager

echo
echo "Pour l'essayer tout de suite :   systemctl start mcpipe-prix"
echo "Pour lire ce qui s'est passé :   journalctl -u mcpipe-prix -n 60"
