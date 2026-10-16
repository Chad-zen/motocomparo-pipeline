#!/usr/bin/env bash
# Condition de départ de mcpipe-taches.service : vrai s'il y a une demande en
# attente. Une requête psql de quelques millisecondes, au lieu de charger Python
# et ses bibliothèques (12 s de processeur) chaque minute pour ne rien faire.
psql "$DATABASE_URL" -tAc "SELECT 1 FROM tache_demandee WHERE statut = 'demandee' LIMIT 1" | grep -q 1
