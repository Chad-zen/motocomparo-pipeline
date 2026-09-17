@echo off
REM Le relevé quotidien des prix.
REM
REM Ce que le site promet en bas de chaque page — « les prix sont relevés chaque
REM jour chez les marchands » — n'était tenu par rien : aucune tâche planifiée ne
REM l'exécutait, et il fallait que quelqu'un lance la chaîne à la main.
REM
REM `match` n'est PAS dans cette chaîne, à dessein : il dure trois quarts d'heure
REM et demande que le site soit arrêté. Il se lance à part, quand une règle de
REM rapprochement change. Sans lui, les prix des fiches existantes sont à jour —
REM c'est exactement ce que la phrase promet — et une offre vraiment nouvelle
REM attend le prochain `match`.
REM
REM `freshness` est le dernier et il n'est pas optionnel : il recalcule le prix de
REM tête de chaque fiche et rafraîchit `product_stats`, la vue d'où sortent tous
REM les prix affichés en liste.
cd /d "C:\Users\Sofia\motocomparo-pipeline"

echo ---------------------------------------------- >> ops\prix.log
echo %DATE% %TIME%  debut >> ops\prix.log

".venv\Scripts\mcpipe.exe" fetch      >> ops\prix.log 2>&1
".venv\Scripts\mcpipe.exe" load       >> ops\prix.log 2>&1
".venv\Scripts\mcpipe.exe" normalize  >> ops\prix.log 2>&1
".venv\Scripts\mcpipe.exe" signature  >> ops\prix.log 2>&1
".venv\Scripts\mcpipe.exe" freshness  >> ops\prix.log 2>&1

echo %DATE% %TIME%  fin >> ops\prix.log
