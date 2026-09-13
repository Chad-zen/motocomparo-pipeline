"""Balayage systematique des fiches du site v2."""
import re, sys, urllib.request, collections, random
from dotenv import load_dotenv; load_dotenv(r'C:/Users/Sofia/motocomparo-pipeline/.env')
sys.path.insert(0, 'src')
from mcpipe.db import connect
from psycopg.rows import dict_row

BASE = 'http://127.0.0.1:8000'
def get(p):
    return urllib.request.urlopen(BASE+p, timeout=30).read().decode('utf-8')

c = connect()
with c.cursor(row_factory=dict_row) as cur:
    cur.execute('''SELECT p.slug, p.colour_code, p.brand_code, c.label_fr AS cat
                   FROM product p JOIN product_stats s ON s.product_id=p.id
                   JOIN category c ON c.id=p.category_id
                   WHERE s.merchant_count>=2 ORDER BY md5(p.id::text) LIMIT 400''')
    echant = cur.fetchall()
c.close()

d = collections.Counter(); ex = collections.defaultdict(list)
def note(cle, slug):
    d[cle] += 1
    if len(ex[cle]) < 3: ex[cle].append(slug)

for r in echant:
    try:
        h = get('/p/' + r['slug'])
    except Exception as e:
        note('page en erreur', r['slug']); continue

    nom = (re.search(r'<h1>([^<]*)</h1>', h) or [None,''])[1].strip()
    tailles = [b[1] for b in re.findall(r'data-taille="([^"]*)">([^<]*)</button>', h)]
    tailles = [t for t in tailles if t != 'Toutes']
    lignes = re.findall(r'<tr class="([^"]*)"\s+data-taille="([^"]*)"\s+data-prix="([^"]*)"\s+data-nb="(\d+)"', h)

    if not nom: note('nom vide', r['slug'])
    elif len(nom) < 3: note('nom d un ou deux caracteres', r['slug'])
    elif re.fullmatch(r'[\d\s\W]+', nom): note('nom uniquement numerique', r['slug'])
    if re.search(r'\b(veste|blouson|gants?|pantalon|bottes?|casque|sacoche|support)\b', nom, re.I):
        note('mot de categorie dans le nom', r['slug'])

    if 'pas de visuel' in h: note('aucune photo', r['slug'])
    if 'Aucune offre disponible' in h: note('aucune offre affichee', r['slug'])
    if not lignes: note('tableau des offres vide', r['slug'])

    if len(tailles) == 1: note('une seule taille proposee', r['slug'])
    systemes = set()
    for t in tailles:
        if re.fullmatch(r'[A-Z]{1,3}L?|XS|S|M|L', t): systemes.add('lettre')
        elif re.fullmatch(r'\d{1,2}', t): systemes.add('chiffre')
        elif re.fullmatch(r'T\d{1,2}', t): systemes.add('T+chiffre')
        elif re.fullmatch(r'EU\d+', t): systemes.add('EU')
        else: systemes.add('autre')
    if len(systemes) > 1: note('systemes de taille melanges', r['slug'])

    sans_taille = sum(int(n) for _cl, t, _p, n in lignes if not t or t == '—')
    total = sum(int(n) for *_x, n in lignes)
    if total and sans_taille == total and tailles: note('toutes les offres sans taille', r['slug'])

    prix = [float(p) for _cl, _t, p, _n in lignes if p]
    if prix and max(prix) > 12 * min(prix): note('ecart de prix > x12 (suspect)', r['slug'])
    if len(prix) < len(lignes): note('offre sans prix', r['slug'])

    if r['colour_code'] == 'unknown': note('produit sans couleur', r['slug'])

print(f'FICHES EXAMINEES : {len(echant)}\n')
for cle, n in d.most_common():
    print(f'  {cle:36} {n:>4}  ({100*n/len(echant):5.1f} %)')
    for s in ex[cle]: print(f'        {s[:64]}')
