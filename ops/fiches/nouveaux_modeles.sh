#!/usr/bin/env bash
# Les marques qui ont des casques COMPARABLES (2 marchands ou plus) sans texte ecrit : le travail de la semaine.
# usage : bash ops/fiches/nouveaux_modeles.sh            (liste par marque)
#         bash ops/fiches/nouveaux_modeles.sh agv        (les modeles sans texte d'une marque)
set -euo pipefail
cd "$(dirname "$0")/../.."
set +e; set -a; . ./.env 2>/dev/null; set +a; set -e
SSH="ssh -i $HOME/.ssh/motocomparo_vps $VPS_USER@$VPS_HOST"
SANS_TEXTE="NOT EXISTS (SELECT 1 FROM fiche_enrichie f WHERE f.brand_code = p.brand_code AND s.best_title ~* f.motif)"

if [ $# -eq 0 ]; then
  $SSH "sudo -u mcpipe psql -d mcpipe -c \"\\copy (SELECT p.brand_code AS marque, count(*) AS fiches_sans_texte, min(s.cheapest)::int AS prix_mini FROM product p JOIN product_stats s ON s.product_id = p.id WHERE p.category_id IN (1,2,3,4,5) AND p.status <> 'merged' AND s.merchant_count >= 2 AND $SANS_TEXTE GROUP BY 1 ORDER BY 2 DESC) TO STDOUT CSV HEADER\""
else
  M="$1"
  $SSH "sudo -u mcpipe psql -d mcpipe -c \"\\copy (SELECT s.merchant_count AS marchands, s.cheapest::int AS prix_mini, s.best_title AS titre FROM product p JOIN product_stats s ON s.product_id = p.id WHERE p.brand_code = '$M' AND p.category_id IN (1,2,3,4,5) AND p.status <> 'merged' AND s.merchant_count >= 2 AND $SANS_TEXTE ORDER BY s.best_title) TO STDOUT CSV HEADER\""
fi
