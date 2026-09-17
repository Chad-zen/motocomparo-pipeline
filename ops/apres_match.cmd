@echo off
REM Ce qu'il faut enchaîner après un `mcpipe match`, dans cet ordre.
REM
REM `freshness` n'est pas optionnel : c'est lui qui recalcule le prix de tête de
REM chaque fiche ET qui rafraîchit `product_stats`, la vue d'où sortent TOUS les
REM prix affichés en liste. Sans lui, le site montre le catalogue d'avant.
cd /d "C:\Users\Sofia\motocomparo-pipeline"

echo === freshness ===
".venv\Scripts\mcpipe.exe" freshness

echo.
echo === verify ===
".venv\Scripts\mcpipe.exe" verify

echo.
echo === mesure du catalogue, comparee a l'avant ===
".venv\Scripts\python.exe" ops\mesure_catalogue.py ops\apres.json ops\avant.json
