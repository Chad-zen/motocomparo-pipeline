#!/usr/bin/env bash
# Exporte, pour une marque, les quatre jeux de donnees dont le redacteur a besoin, LIMITES aux casques sans texte ecrit.
# usage : bash ops/fiches/export_marque.sh agv        -> scratch/nouveaux/agv/{fiches,descriptions,sharp,revendeur}.csv
set -euo pipefail
M="$1"
cd "$(dirname "$0")/../.."
set +e; set -a; . ./.env 2>/dev/null; set +a; set -e
SSH="ssh -i $HOME/.ssh/motocomparo_vps $VPS_USER@$VPS_HOST"
D=scratch/nouveaux/$M
mkdir -p "$D"
SANS_TEXTE="NOT EXISTS (SELECT 1 FROM fiche_enrichie f WHERE f.brand_code = p.brand_code AND s.best_title ~* f.motif)"

# 1. les fiches comparables sans texte ecrit
$SSH "sudo -u mcpipe psql -d mcpipe -c \"\\copy (SELECT p.id, s.cheapest::int, s.merchant_count, c.code, s.best_title FROM product p JOIN product_stats s ON s.product_id=p.id JOIN category c ON c.id=p.category_id WHERE p.brand_code='$M' AND p.category_id IN (1,2,3,4,5) AND p.status <> 'merged' AND s.merchant_count>=2 AND $SANS_TEXTE ORDER BY s.best_title) TO STDOUT CSV HEADER\"" > "$D/fiches.csv"

# 2. les descriptions des flux marchands (une par texte distinct) : la matiere premiere des faits
$SSH "sudo -u mcpipe psql -d mcpipe -c \"\\copy (SELECT DISTINCT ON (m.code, md5(s.row->>'description')) m.code, s.row->>'title', left(regexp_replace(regexp_replace(coalesce(s.row->>'description',''),'<[^>]+>',' ','g'),'[[:space:]]+',' ','g'),1800) FROM stg_feed_row s JOIN merchant m ON m.id=s.merchant_id WHERE regexp_replace(lower(s.row->>'brand'),'[^a-z0-9]','','g') LIKE '$M%' AND length(coalesce(s.row->>'description',''))>60 AND s.row->>'title' ~* '(casque|helmet)' ORDER BY m.code, md5(s.row->>'description')) TO STDOUT CSV HEADER\"" > "$D/descriptions.csv"

# 3. les tests SHARP de la marque
$SSH "sudo -u mcpipe psql -d mcpipe -c \"\\copy (SELECT modele, etoiles, poids_g, tailles, type_casque, materiaux, norme, date_test, options FROM source_sharp WHERE regexp_replace(lower(marque),'[^a-z0-9]','','g') LIKE '$M%' ORDER BY modele) TO STDOUT CSV HEADER\"" > "$D/sharp.csv"

# 4. le tableau technique du revendeur
$SSH "sudo -u mcpipe psql -d mcpipe -c \"\\copy (SELECT modele, type_annonce, nombre_coques, fermeture, matiere, fonctionnalites, poids_g, homologation FROM source_revendeur WHERE regexp_replace(lower(marque),'[^a-z0-9]','','g') LIKE '$M%' ORDER BY modele) TO STDOUT CSV HEADER\"" > "$D/revendeur.csv"

wc -l "$D"/*.csv
