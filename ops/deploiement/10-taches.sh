#!/usr/bin/env bash
# Installe l'exécuteur des calculs demandés depuis /admin/calculs.
# À lancer en root sur le serveur, APRÈS avoir appliqué sql/034_taches.sql.
set -euo pipefail
d="$(cd "$(dirname "$0")" && pwd)/systemd"
install -m 644 "$d/mcpipe-taches.service" /etc/systemd/system/
install -m 644 "$d/mcpipe-taches.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mcpipe-taches.timer
systemctl list-timers mcpipe-taches.timer --no-pager
