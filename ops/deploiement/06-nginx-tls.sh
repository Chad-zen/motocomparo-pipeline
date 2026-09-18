#!/usr/bin/env bash
# 06 — La façade : nginx, le CACHE, puis HTTPS.
#
#   DOMAINE=staging.motocomparo.com NOINDEX=1 bash 06-nginx-tls.sh
#
# En production, avec le www et sans le noindex :
#
#   DOMAINE=motocomparo.com ALIAS=www.motocomparo.com bash 06-nginx-tls.sh
#
# NOINDEX=1 pour un site d'essai, rien pour la production.
#
# C'est l'étape qui décide de la vitesse du site. Le reste est de la plomberie.
set -euo pipefail

DOMAINE="${DOMAINE:-}"
[ -z "$DOMAINE" ] && { echo "DOMAINE=<nom> [ALIAS=www.<nom>] [NOINDEX=1] bash 06-nginx-tls.sh"; exit 1; }

# Un SECOND nom, facultatif. En pratique le « www ».
#
# Il n'existait pas, et l'oubli ne se voyait pas tant qu'on ne servait qu'un
# sous-domaine de test : personne ne tape « www.staging ». Sur un nom de domaine
# ordinaire, en revanche, une partie des visiteurs et à peu près tous les vieux
# liens passent par le www — et un nom absent du `server_name` ET du certificat
# ne donne pas une page moche, il donne un AVERTISSEMENT DE SÉCURITÉ du
# navigateur. C'est la pire page d'accueil possible.
#
# Les deux noms sont servis par le même bloc et couverts par le même
# certificat ; la redirection de l'un vers l'autre est posée plus bas, pour que
# les moteurs n'aient qu'une seule adresse à indexer.
ALIAS="${ALIAS:-}"
# Vers quel nom on redirige l'autre. Par défaut l'apex, sans www : c'est le plus
# court, et c'est celui que le site s'annonce déjà à lui-même.
CANONIQUE="${CANONIQUE:-$DOMAINE}"
NOMS="$DOMAINE"
[ -n "$ALIAS" ] && NOMS="$DOMAINE $ALIAS"

install -d -o www-data -g www-data /var/cache/nginx/motocomparo

cat > /etc/nginx/conf.d/motocomparo-cache.conf <<'CACHECONF'
# Le cache de pages.
#
# Mesuré le 2026-09-14 : sans cache, l'accueil mettait 12 s, la recherche 16 s,
# les bons plans 17 s — sur une machine à 12 cœurs. Le VPS en a UN. Servir des
# pages déjà fabriquées n'est donc pas une optimisation, c'est la condition pour
# que le site tienne debout.
#
# keys_zone=10m : environ 80 000 pages référencées, largement au-delà du besoin.
# max_size=1g   : le disque fait 50 Go, on en prend 1.
# inactive=24h  : une fiche que personne n'ouvre de la journée sort du cache.
proxy_cache_path /var/cache/nginx/motocomparo levels=1:2
                 keys_zone=mc:10m max_size=1g inactive=24h use_temp_path=off;
CACHECONF

# Vide en production, l'en-tete d'interdiction sur un site d'essai.
if [ "${NOINDEX:-0}" = "1" ]; then
    ENTETE_NOINDEX='add_header X-Robots-Tag "noindex, nofollow" always;'
else
    ENTETE_NOINDEX=''
fi

cat > /etc/nginx/sites-available/motocomparo <<CONF
server {
    listen 80;
    listen [::]:80;
    server_name ${NOMS};

    # Un seul nom pour les moteurs. Servir la MÊME page sous deux adresses les
    # met en concurrence l'une avec l'autre : le moteur en choisit une, pas
    # forcément celle qu'on voulait, et partage l'autorité entre les deux.
    # La redirection est permanente (301) et garde le chemin et la requête.
    # AUCUN ACCENT GRAVE DANS CE COMMENTAIRE, ET C'EST LA CINQUIEME FOIS.
    #
    # Ce bloc est ecrit dans un heredoc NON quote : il le faut, pour que le nom
    # de domaine y soit remplace. Tout y est donc interprete par bash AVANT
    # d'atteindre nginx, et deux choses s'y perdent :
    #
    #   - les variables nginx, d'ou les dollars echappes plus bas ;
    #   - les ACCENTS GRAVES, que bash lit comme une substitution de commande.
    #     Un accent grave pose autour d'un nom de variable dans une EXPLICATION
    #     fait executer ce nom comme une commande, et le script meurt sur
    #     "unbound variable" en designant la premiere ligne du heredoc, jamais
    #     la ligne fautive. On cherche alors tres loin de la cause.
    #
    # Verifie en syntaxe le jour ou cette ligne a ete ecrite : bash -n ne
    # developpe rien, il ne pouvait pas le voir. Seul l'appel reel l'a montre.
    if (\$host != ${CANONIQUE}) {
        return 301 https://${CANONIQUE}\$request_uri;
    }

    # Les pages sont déjà compressées par nginx ; les images viennent des
    # marchands et ne passent pas par ici.
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;

    # NOINDEX=1 : un site d'essai ne doit PAS etre indexe. Il sert le meme
    # catalogue que la production ; laisse ouvert, il lui ferait concurrence
    # sur ses propres pages. L'en-tete couvre TOUT — le plan du site et les
    # fichiers compris — la ou un robots.txt ne couvre que ce qu'il nomme.
    #
    # Il est repete dans chaque bloc location qui pose deja un add_header :
    # chez nginx, un add_header dans un bloc enfant EFFACE ceux du parent. Pose
    # une seule fois ici, il ne sortait sur aucune page.
    # (Sans accent grave autour de ces deux mots : voir l'avertissement plus
    # haut, bash les executerait comme des commandes.)
    ${ENTETE_NOINDEX}
    # --- En-tetes de securite ---
    # Poses a la main sur le serveur le 17/09, donc perdus au prochain passage
    # de ce script : ils vivent ici desormais. Repetes dans chaque bloc pour la
    # meme raison que le noindex ci-dessus.
    #
    # HSTS : le navigateur refuse le HTTP sur ce nom pendant un an. Il s'en
    # souvient, et c'est pourquoi on ne met pas preload, qui est irreversible a
    # l'echelle des navigateurs.
    #
    # Pas de Content-Security-Policy : le site pose ses scripts en ligne dans
    # les gabarits, une CSP devrait donc autoriser unsafe-inline et n'aurait
    # plus grand effet. Une CSP de facade vaut moins que son absence, parce
    # qu'elle fait croire la question reglee.
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    access_log /var/log/nginx/motocomparo.access.log;
    error_log  /var/log/nginx/motocomparo.error.log;

    # Les fichiers du site (CSS, logo, la bibliothèque du graphique) ne changent
    # que lorsque leur adresse change — elle porte un numéro de version. On peut
    # donc dire aux navigateurs de les garder un an.
    location /static/ {
        alias /srv/motocomparo/app/src/mcsite/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        ${ENTETE_NOINDEX}
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        # La cle du cache doit porter le NOM D'HOTE. Par defaut nginx
        # utilise \$proxy_host, c'est-a-dire 127.0.0.1:8000 pour toutes les
        # requetes : une page demandee par l'adresse IP etait resservie telle
        # quelle pour le domaine — le plan du site annoncait des adresses en
        # <ip-vps> aux visiteurs du nom de domaine. Le schema y est aussi,
        # sans quoi une page servie en http reviendrait en https.
        proxy_cache_key "\$scheme\$host\$request_uri";

        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_cache mc;
        # Une heure. Les prix sont relevés une fois par jour : une page d'une
        # heure ne ment pas. Le cache est de toute façon vidé à la fin du relevé
        # quotidien (voir 07-planification.sh), donc un prix neuf est visible
        # tout de suite après la collecte.
        proxy_cache_valid 200 301 302 1h;
        proxy_cache_valid 404 1m;

        # DEUX réglages qui font tout le travail sur une machine à un cœur :
        #
        # proxy_cache_use_stale : si l'application est occupée, en erreur, ou
        #   en train de redémarrer, on continue de servir la version en cache.
        #   Un visiteur ne voit jamais une page blanche pendant que le pipeline
        #   tourne.
        # proxy_cache_background_update : la page périmée est servie
        #   IMMÉDIATEMENT et rafraîchie derrière. Personne n'attend jamais la
        #   reconstruction.
        #
        # Aucun accent grave dans ce bloc : il est volontairement NON protégé,
        # pour que le nom de domaine soit remplacé, et bash y prendrait un
        # accent grave pour une commande à exécuter. C'est arrivé au premier
        # déploiement, le 2026-09-17.
        proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
        proxy_cache_background_update on;

        # Cent visiteurs qui arrivent en même temps sur une page absente du
        # cache : un seul la demande à l'application, les autres attendent son
        # résultat. Sans ça, un cœur unique reçoit cent fois la même requête.
        proxy_cache_lock on;
        proxy_cache_lock_timeout 20s;

        # Pour voir, dans le navigateur, si la page vient du cache : HIT, MISS,
        # UPDATING, STALE. C'est le seul moyen de vérifier que tout ceci sert.
        add_header X-Cache \$upstream_cache_status;
        ${ENTETE_NOINDEX}
        # Troisieme repetition : ce bloc pose son propre add_header, donc il
        # efface ceux du parent. C'est le bloc qui sert les PAGES.
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;

        proxy_read_timeout 60s;
    }
}
CONF

ln -sf /etc/nginx/sites-available/motocomparo /etc/nginx/sites-enabled/motocomparo
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo
echo "== certificat HTTPS =="
echo "   ⚠ Le DNS de ${NOMS} doit DÉJÀ pointer sur ce VPS, sinon certbot"
echo "     échoue et il faudra recommencer. Vérifier d'abord :"
for n in ${NOMS}; do echo "        dig +short $n"; done
echo
read -r -p "   Le DNS est-il basculé ? [o/N] " reponse
if [ "$reponse" = "o" ] || [ "$reponse" = "O" ]; then
    # `-d` par nom : un certificat qui ne couvre pas le www fait afficher un
    # avertissement de sécurité à qui l'utilise.
    certbot --nginx $(for n in ${NOMS}; do printf -- '-d %s ' "$n"; done)             --redirect --agree-tos --no-eff-email
    systemctl reload nginx
    echo "   certificat en place, renouvellement automatique actif"
else
    echo "   certificat reporté. Relancer plus tard :"
    echo "        certbot --nginx $(for n in ${NOMS}; do printf -- '-d %s ' "$n"; done)--redirect"
fi

echo
echo "OK. Étape suivante : bash 07-planification.sh"
