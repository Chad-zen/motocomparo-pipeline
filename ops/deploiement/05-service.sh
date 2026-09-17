#!/usr/bin/env bash
# 05 — Le service qui tient le site debout.
#
#   bash 05-service.sh
#
# systemd relance l'application si elle tombe, et la redémarre au reboot. Sans
# ça, un plantage à 3 h du matin laisse le site éteint jusqu'à ce que quelqu'un
# s'en aperçoive.
set -euo pipefail

cat > /etc/systemd/system/mcsite.service <<'UNIT'
[Unit]
Description=MotoComparo — le site
After=network.target postgresql@18-main.service
Wants=postgresql@18-main.service

[Service]
Type=exec
User=motocomparo
Group=motocomparo
WorkingDirectory=/srv/motocomparo/app
EnvironmentFile=/srv/motocomparo/.env

# UN SEUL worker, et c'est délibéré : le VPS a un seul cœur. En ajouter ne
# rendrait pas les pages plus vite, ça ne ferait que multiplier la mémoire et
# les connexions à la base. Ce qui rend le site rapide, c'est le cache de nginx
# devant, pas le nombre de processus derrière.
ExecStart=/srv/motocomparo/venv/bin/uvicorn mcsite.app:app \
          --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers \
          --forwarded-allow-ips 127.0.0.1

Restart=always
RestartSec=3

# Le service ne peut écrire nulle part ailleurs que dans ses propres dossiers.
# Si l'application est un jour compromise, elle est compromise dans une boîte.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/srv/motocomparo
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now mcsite.service
sleep 3
systemctl --no-pager --lines=15 status mcsite.service || true

echo
echo "Vérification directe (sans nginx) :"
curl -sS -o /dev/null -w "   http://127.0.0.1:8000/  ->  HTTP %{http_code} en %{time_total}s\n" \
     --max-time 30 http://127.0.0.1:8000/ || echo "   pas de réponse — voir: journalctl -u mcsite -n 50"

echo
echo "OK. Étape suivante : bash 06-nginx-tls.sh"
