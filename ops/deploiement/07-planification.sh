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
# FC-Moto est telecharge A PART. Son serveur met de 4 minutes a plus d'une
# heure et demie selon les nuits (95 min le 15/10, 99 min le 17/10) et a coupe la
# connexion le 16/10 : la chaine, qui attendait chaque fichier l'un apres
# l'autre, laissait les prix des CINQ autres marchands vieillir de deux heures
# de plus. Les cinq autres sont donc traites d'abord ; FC-Moto repart derriere,
# quand son fichier est la, avec la meme suite d'etapes (`traiter`). Coupure a
# 2 h 20 : au-dela, la copie de la veille reste, comme avant.
AUTRES="speedway labecanerie motoblouz maxxess motoaxxe"
# LES MARCHANDS NEUFS (19/10/2026). Motard Bleu n'a pas encore de nuits a son actif : il est
# traite avec les autres, mais ISOLE. Un echec de son telechargement, de son chargement ou de
# sa normalisation s'ecrit dans le journal et la chaine continue, alors que `set -e` arrete
# tout pour les marchands eprouves. Sa cle de flux vient d'un fichier a part, charge par un
# drop-in de l'unite (`ops/deploiement/11-motardbleu.sh`) : jamais dans le `.env` principal,
# sinon un `mcpipe fetch` lance sans `--only` le telechargerait aussi.
# Motoin (20/10/2026) rejoint la liste : meme isolement. Son URL vient de `12-motoin.sh`
# (fichier d'environnement a part, drop-in systemd), jamais du `.env` principal.
NEUFS="motardbleu motoin"
FC_LOG=/var/tmp/mcpipe-fetch-fcmoto.log
( timeout 8400 mcpipe fetch --only fcmoto >"$FC_LOG" 2>&1     || echo "!!! fetch fcmoto en echec ou trop long, copie de la veille gardee" >>"$FC_LOG" ) &
FC_PID=$!
for c in $AUTRES $NEUFS; do
  mcpipe fetch --only "$c" || echo "!!! fetch $c en echec, chaine poursuivie"
done

traiter() {   # $1 : les marchands a charger ; $2 : les marchands neufs, isoles
  local c
  for c in $1; do
    mcpipe load --only "$c"
    mcpipe normalize --only "$c"
    mcpipe signature --only "$c"   # porte les tailles ; doit précéder enrich
  done
  # Un marchand neuf qui echoue garde l'etat de la veille (ses offres ne sont pas retirees :
  # `normalize` n'a pas tourne) et la chaine des autres continue.
  for c in ${2:-}; do
    ( mcpipe load --only "$c" && mcpipe normalize --only "$c" && mcpipe signature --only "$c" ) \
      || echo "!!! $c en echec (chargement, normalisation ou signature), chaine poursuivie"
  done
  mcpipe enrich         # catégories + emprunt des tailles au code-barres
  # Le rapprochement INCRÉMENTAL (6 minutes le 16/10/2026, site en ligne) : il ne
  # traite que les offres neuves, les fiches existantes ne bougent pas. Sans lui,
  # plus aucun produit nouveau n'entrait au catalogue depuis le 1er octobre. Le
  # `||` est voulu, comme pour les alertes : un échec s'écrit dans le journal et
  # la chaîne des prix continue.
  nice -n 10 mcpipe match --sans-mpn || echo "!!! mcpipe match en echec, chaine poursuivie"
  # Les pieces de casque (coussinets, pare-soleil, pics...) qui viennent d'etre rattachees a
  # une fiche casque : `enrich` ne corrige que les offres, pas les fiches deja creees.
  mcpipe accessoires-casque --appliquer || echo "!!! mcpipe accessoires-casque en echec, chaine poursuivie"
  # Les fiches qui se dédoublent pour un même code-barres : fusionne ce que la
  # propriétaire a VALIDÉ dans /admin/regroupements (et, si elle l'a activée, ce
  # que le site juge sûr), puis recalcule les propositions et les alias de marque
  # à lui soumettre. Doit précéder `relier-tailles` et `freshness`.
  # Un meme casque coupe en deux fiches par tailles (XS-S sur l'une, M-L sur l'autre) : regle stricte,
  # voir src/mcpipe/tailles_coupees.py. Inscrit les paires comme validees ; `consolider` les fusionne.
  mcpipe fusion-tailles --inscrire || echo "!!! mcpipe fusion-tailles en echec, chaine poursuivie"
  nice -n 10 mcpipe consolider --appliquer || echo "!!! mcpipe consolider en echec, chaine poursuivie"
  mcpipe relier-tailles # relit les overrides de taille issus de l'emprunt
                        # et rattache chaque offre a la bonne variante —
                        # sans cela, les tailles empruntees depuis fcmoto ne
                        # s'affichent jamais : l'emprunt ecrit dans offer_size_override,
                        # mais le site lit variant.size_code, pose par cette etape.
  mcpipe freshness      # recalcule les prix affichés — jamais optionnel
  # Les bons plans, calcules UNE fois ici (14 a 30 s) et ranges dans une table : la page
  # /bons-plans ne fait plus que lire 48 lignes. A lancer apres `freshness` (les prix).
  mcpipe bons-plans || echo "!!! mcpipe bons-plans en echec, la page calcule alors a la demande"
  # Les tailles achetables, rangees dans une table : les pages filtrees par taille la lisent. Apres
  # `freshness` (elle depend des offres vivantes et de leurs prix). Sans elle : calcul a la demande.
  mcpipe tailles-achetables || echo "!!! mcpipe tailles-achetables en echec, les filtres de taille calculent a la demande"

}

traiter "$AUTRES" "$NEUFS"
wait "$FC_PID" || true
cat "$FC_LOG"
traiter fcmoto
# Les fiches dont deux marchands sont a plus de 50 % d'ecart : listees dans
# `controle_ecart` pour relecture (rien n'est separe). Demande de la proprietaire,
# 22/10/2026, apres le pinlock Airoh rattache a la visiere.
mcpipe controle-ecarts || echo "!!! mcpipe controle-ecarts en echec, chaine poursuivie"
# Les alertes de prix lisent les prix que freshness vient de poser. Le `||` est
# voulu : un serveur d'envoi en panne ne doit pas priver le site des
# caracteristiques du jour. La commande elle-meme ne sort en erreur que sur une
# panne de base ; l'echec s'ecrit dans le journal, la chaine continue.
mcpipe alertes || echo "!!! mcpipe alertes en echec, chaine poursuivie"
mcpipe caracteristiques  # relit les descriptions du jour, remplit product_caracteristique
                         # LIT LES FICHIERS SUR DISQUE : doit tourner apres fetch,
                         # tant qu'ils n'ont pas ete ecrases par le prochain fetch.
                         # Travaille par fiche deja appariee : linked_status = 'linked'
                         # est pose par match, pas remis a zero chaque nuit.
# Quelles fiches n'ont pas de matière, de saison ou d'homologation : alimente
# l'écran « Fiches sans caractéristiques » de l'administration.
# Les mesures SHARP (note, poids pese) et le tableau du revendeur se COLLENT sur les fiches par
# rapprochement ; ce rapprochement n'etait dans aucune chaine, et le grand recalcul du 18/10/2026 a
# efface ses 6 000 valeurs sans que personne le voie (constate le 22/10/2026). Rejouable, 2 secondes
# chacun, place apres `caracteristiques` qui ne touche pas a ces deux sources.
mcpipe sharp-rapprocher || echo "!!! mcpipe sharp-rapprocher en echec, chaine poursuivie"
mcpipe revendeur-rapprocher || echo "!!! mcpipe revendeur-rapprocher en echec, chaine poursuivie"
mcpipe couverture || echo "!!! mcpipe couverture en echec, chaine poursuivie"

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
# Le cache de l'APPLICATION (SITE_CACHE_TTL, 3 h depuis le 16/10/2026) garde
# aussi les listes : on redémarre le site pour qu'il reparte des nouveaux prix,
# et son ExecStartPost (mcsite-rechauffer) reconstruit le cache aussitôt. Avant,
# le cache expirait toutes les 10 min et le visiteur suivant attendait 6 à 7 s
# sur /bons-plans ou la recherche (audit du 16/10/2026).
ExecStartPost=+/usr/bin/systemctl restart mcsite.service

# Le VPS a UN cœur, partagé avec le site. On met le pipeline derrière les
# visiteurs : il ira un peu moins vite, personne ne verra la différence, et une
# page ne restera pas bloquée derrière un téléchargement de 270 Mo.
Nice=10
IOSchedulingClass=idle

# Une chaîne qui dépasse quatre heures et demie est une chaîne en panne. On la
# coupe plutôt que de la laisser tenir la machine jusqu'au lendemain. (Trois
# heures jusqu'au 19/10/2026 : ce jour-là, FC-Moto 82 min + emprunt des tailles
# 28 min + match 20 min + contrôle 13 min ont fait couper la chaîne à 07h04.)
TimeoutStartSec=4h30min
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
