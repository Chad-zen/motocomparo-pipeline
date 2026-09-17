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

# Les variables viennent de systemd (`EnvironmentFile`), et surtout PAS d'un
# `. /srv/motocomparo/.env`. Sourcer un fichier de configuration, c'est
# l'EXECUTER : une valeur contenant une espace — le nom de l'editeur dans
# MENTIONS_EDITEUR, par exemple — faisait chercher une commande portant le
# second mot, et toute la chaine s'arretait avant le premier telechargement.
#
# (Le nom reel etait ecrit ici, en clair, dans un depot PUBLIC. Retire. Le depot
# est anonymise : aucun nom, aucune adresse personnelle n'y a sa place, pas meme
# dans un commentaire qui explique une panne.) systemd lit des paires cle=valeur sans rien
# executer. Constate au premier essai reel, le 2026-09-17 — et c'est
# exactement pour ca qu'on essaie une tache planifiee au lieu de l'attendre.

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

# Le vidage du cache est fait par systemd APRÈS cette chaîne, voir
# `ExecStartPost` dans l'unité. Il était ici, et il ne faisait RIEN : le cache
# appartient à `www-data`, la chaîne tourne sous `motocomparo`, et le
# `2>/dev/null || true` avalait le refus. Les pages restaient donc figées
# jusqu'à expiration — une fiche affichait encore les prix de la veille une
# heure après la collecte. Constaté le 2026-09-17, en comparant la page servie
# et la page reconstruite.
#
# Une erreur qu'on fait taire est une erreur qu'on ne voit jamais.

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
EnvironmentFile=/srv/motocomparo/.env
ExecStart=/usr/local/bin/mcpipe-prix

# Le cache de nginx garde les pages une heure ; après une collecte elles sont
# périmées. Le « + » fait exécuter cette ligne en root malgré le `User=`
# ci-dessus : c'est le seul moyen pour que le compte applicatif, qui n'a aucun
# droit sur /var/cache/nginx, déclenche quand même le vidage.
ExecStartPost=+/usr/bin/find /var/cache/nginx/motocomparo -type f -delete

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
