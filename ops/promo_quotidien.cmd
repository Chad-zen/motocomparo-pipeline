@echo off
REM Relevé quotidien des codes promo chez les marchands.
REM Enregistré dans le planificateur de tâches Windows sous « MotoComparo - codes promo ».
REM Le journal s'écrit à côté, pour qu'un échec se voie sans ouvrir un terminal.
cd /d "C:\Users\Sofia\motocomparo-pipeline"
echo ---------------------------------------------- >> ops\promo.log
echo %DATE% %TIME% >> ops\promo.log
".venv\Scripts\mcpipe.exe" promo >> ops\promo.log 2>&1
