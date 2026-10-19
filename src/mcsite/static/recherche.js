/* La barre de recherche qui propose des chemins.
   ==========================================================================

   Le principe, repris d'idealo et d'Amazon : on ne devine pas ce que quelqu'un
   cherche, on lui montre ce qui existe. Taper « arai » ne renvoie pas
   seulement 147 produits en vrac — ça répond « Arai, et il y en a 94 dans les
   casques intégraux, 15 en cross, 14 en jet », et on choisit.

   C'est l'entonnoir : une marque, puis le rayon, sans quitter la recherche.

   TROIS CHOSES QUI COMPTENT PLUS QUE L'AFFICHAGE
   ==============================================

   1. **On attend que la frappe se calme.** Sans cela, « alpinestars » lance
      onze requêtes dont dix sont périmées avant d'arriver.
   2. **La requête précédente est annulée.** Sinon la réponse de « ara » peut
      arriver APRÈS celle de « arai » et réécrire la liste avec des résultats
      plus anciens — un bug qui ne se voit qu'en connexion lente, c'est-à-dire
      chez les visiteurs qu'on sert le plus mal.
   3. **Tout se fait au clavier.** Flèches, Entrée, Échap. Une liste qu'on ne
      peut parcourir qu'à la souris n'existe pas pour une partie des visiteurs,
      et elle est pénible pour tous les autres.
   ====================================================================== */

(function () {
  'use strict';

  var ATTENTE = 160;       // ms de calme avant d'interroger le serveur
  var MINIMUM = 2;         // en dessous, tout correspond : on ne propose rien

  function euros(v) {
    if (v === null || v === undefined) return '';
    return v.toLocaleString('fr-FR',
      { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
  }

  function elem(balise, classe, texte) {
    var e = document.createElement(balise);
    if (classe) e.className = classe;
    if (texte !== undefined) e.textContent = texte;
    return e;
  }

  function installer(form) {
    var champ = form.querySelector('input[name="q"]');
    if (!champ) return;

    var liste = elem('div', 'sugg');
    liste.id = 'sugg-' + Math.random().toString(36).slice(2, 8);
    liste.setAttribute('role', 'listbox');
    liste.hidden = true;
    form.appendChild(liste);

    // Le motif « combobox » : le champ annonce qu'il commande une liste, et
    // dit laquelle de ses options est active. Sans ces attributs, un lecteur
    // d'écran voit un champ de texte ordinaire et ne dira jamais qu'il y a
    // douze propositions en dessous.
    champ.setAttribute('role', 'combobox');
    champ.setAttribute('aria-expanded', 'false');
    champ.setAttribute('aria-controls', liste.id);
    champ.setAttribute('aria-autocomplete', 'list');
    champ.setAttribute('autocomplete', 'off');

    var dit = elem('p', 'visuellement-cache');
    dit.setAttribute('role', 'status');
    dit.setAttribute('aria-live', 'polite');
    form.appendChild(dit);

    var minuteur = null, encours = null, choisi = -1, options = [];

    function fermer() {
      liste.hidden = true;
      champ.setAttribute('aria-expanded', 'false');
      champ.removeAttribute('aria-activedescendant');
      choisi = -1;
    }

    function surligner(i) {
      options.forEach(function (o, k) {
        o.classList.toggle('est-choisi', k === i);
        o.setAttribute('aria-selected', String(k === i));
      });
      choisi = i;
      if (i >= 0 && options[i]) {
        champ.setAttribute('aria-activedescendant', options[i].id);
        options[i].scrollIntoView({ block: 'nearest' });
      } else {
        champ.removeAttribute('aria-activedescendant');
      }
    }

    function option(href, dedans, etiquette, conteneur) {
      var a = elem('a', 'sugg__ligne');
      a.href = href;
      a.id = liste.id + '-o' + options.length;
      a.setAttribute('role', 'option');
      a.setAttribute('aria-selected', 'false');
      if (etiquette) a.setAttribute('aria-label', etiquette);
      dedans.forEach(function (n) { a.appendChild(n); });
      (conteneur || liste).appendChild(a);
      options.push(a);
      return a;
    }

    function vignette(p, classe) {
      if (!p.image) return null;
      var v = elem('span', classe);
      var img = document.createElement('img');
      img.src = p.image;
      img.alt = '';
      img.loading = 'lazy';
      img.addEventListener('error', function () { v.remove(); });
      v.appendChild(img);
      return v;
    }

    // LE PANNEAU A DEUX COLONNES (16/10/2026, inspiré de Dafy et Speedway) :
    // à gauche les CHEMINS — le rayon compris dans la phrase, les marques, les
    // rayons —, à droite les PRODUITS, une carte par modèle. L'ancienne liste
    // faisait 310 px de large et trois grandes cartes y prenaient toute la
    // hauteur : les chemins, qui font gagner le plus de temps, passaient sous
    // la ligne de flottaison.
    function colonne(classe) {
      var c = elem('div', classe);
      liste.appendChild(c);
      return c;
    }

    function rubriqueDans(dans, titre) {
      dans.appendChild(elem('p', 'sugg__titre', titre));
    }

    function carte(dans, p) {
      var noeuds = [];
      var v = vignette(p, 'sugg__vignette');
      if (v) noeuds.push(v);
      var corps = elem('span', 'sugg__produit');
      corps.appendChild(elem('span', 'sugg__marque', p.marque));
      corps.appendChild(elem('span', 'sugg__nom', p.nom));
      // « 3 coloris » plutôt que trois lignes jumelles : les fiches d'un même
      // titre sont regroupées côté serveur.
      var dessous = [];
      // un code-barres tape : on dit de QUELLE taille il s'agit
      if (p.taille) dessous.push('Taille ' + p.taille);
      if (p.coloris > 1) dessous.push(p.coloris + ' coloris');
      else if (p.couleur) dessous.push(p.couleur);
      if (p.marchands) dessous.push(p.marchands + ' marchands');
      if (dessous.length) corps.appendChild(elem('span', 'sugg__marchands', dessous.join(' · ')));
      if (p.prix !== null) corps.appendChild(elem('span', 'sugg__prix', 'dès ' + euros(p.prix)));
      noeuds.push(corps);
      var a = option('/p/' + p.slug, noeuds,
        p.marque + ' ' + p.nom + (p.prix !== null ? ', dès ' + euros(p.prix) : ''), dans);
      a.classList.add('sugg__carte');
      return a;
    }

    function peindre(d, texte) {
      liste.innerHTML = '';
      options = [];
      liste.classList.remove('sugg--accueil');
      // Un modèle tapé (« shoei neotec ») : sur téléphone, ses produits passent
      // avant l'entonnoir de la marque, qui prenait tout le premier écran.
      liste.classList.toggle('sugg--modele',
        !!(d.meilleurs && d.meilleurs.length && !d.rayon_compris));
      var gauche = colonne('sugg__chemins');
      var droite = colonne('sugg__produits');

      // LE RAYON COMPRIS : « gant hiver » -> Gants · Hiver (183). C'est la
      // réponse la plus utile quand la phrase décrit un besoin et pas un
      // modèle : la liste filtrée existe, avec ses filtres et son tri.
      if (d.rayon_compris) {
        var rc = d.rayon_compris;
        rubriqueDans(gauche, 'Rayon');
        var l = option(rc.url, [elem('span', 'sugg__quoi', rc.label),
                                elem('span', 'sugg__compte', rc.n)],
          rc.label + ', ' + rc.n + ' produits', gauche);
        l.classList.add('sugg__ligne--rayon');
      }

      // UNE MARQUE TAPÉE SEULE : on propose la marque, pas trois de ses
      // produits pris au hasard.
      if (d.marque_seule) {
        var ms = d.marque_seule;
        rubriqueDans(gauche, 'La marque');
        var lm = option('/m/' + encodeURIComponent(ms.marque),
          [elem('span', 'sugg__quoi', 'Tout ' + ms.marque.toUpperCase()),
           elem('span', 'sugg__compte', ms.n)],
          'Tous les produits ' + ms.marque.toUpperCase() + ', ' + ms.n + ' comparés', gauche);
        lm.classList.add('sugg__ligne--rayon');
      }

      // L'ENTONNOIR : une marque, puis le rayon. Le code de marque part TEL
      // QU'IL EST STOCKÉ, en minuscules — en majuscules, le lien répondait
      // 200 avec zéro produit.
      if (d.entonnoir && d.entonnoir.length && !d.rayon_compris) {
        var marque = d.entonnoir[0].marque;
        rubriqueDans(gauche, marque.toUpperCase() + ', par rayon');
        d.entonnoir.forEach(function (e) {
          option('/c/' + e.rayon_code + '?marque=' + encodeURIComponent(marque),
            [elem('span', 'sugg__quoi', e.rayon), elem('span', 'sugg__compte', e.n)],
            marque.toUpperCase() + ' dans ' + e.rayon + ', ' + e.n + ' produits', gauche);
        });
      }

      if (d.rayons && d.rayons.length) {
        rubriqueDans(gauche, 'Rayons');
        d.rayons.forEach(function (r) {
          option('/c/' + r.code, [elem('span', 'sugg__quoi', r.label)], undefined, gauche);
        });
      }

      // Même garde qu'au-dessus : sans `entonnoir`, lire `.length` sur
      // `undefined` levait une exception et vidait TOUT l'affichage.
      var autres = (d.marques || []).filter(function (m) {
        return !(d.entonnoir && d.entonnoir.length) || m.marque !== d.entonnoir[0].marque;
      });
      if (autres.length) {
        rubriqueDans(gauche, 'Marques');
        autres.forEach(function (m) {
          option('/m/' + encodeURIComponent(m.marque),
            [elem('span', 'sugg__quoi', m.marque.toUpperCase()),
             elem('span', 'sugg__compte', m.n)], undefined, gauche);
        });
      }

      var produits = (d.meilleurs || []).concat(d.produits || []);
      if (produits.length) {
        rubriqueDans(droite, 'Produits');
        var grille = elem('div', 'sugg__grille');
        droite.appendChild(grille);
        produits.slice(0, 8).forEach(function (p) { carte(grille, p); });
      }

      if (!gauche.childNodes.length) gauche.remove();
      if (!droite.childNodes.length) droite.remove();

      // Toujours une sortie vers la liste complète : le panneau ne montre que
      // les premiers résultats, et qui n'y trouve pas son bonheur ne doit pas
      // croire qu'il n'y a rien.
      if (options.length) {
        var tout = option(d.rayon_compris ? d.rayon_compris.url
                                          : '/recherche?q=' + encodeURIComponent(texte),
          [elem('span', 'sugg__tout', d.rayon_compris
            ? 'Voir les ' + d.rayon_compris.n + ' produits'
            : 'Voir tous les résultats pour « ' + texte + ' »')]);
        tout.classList.add('sugg__ligne--tout');
      }

      if (!options.length) { fermer(); dit.textContent = ''; return; }
      ouvrir();
      dit.textContent = options.length + ' proposition' + (options.length > 1 ? 's' : '');
    }

    // LE CHAMP VIDE N'EST PLUS MUET : les recherches récentes de ce visiteur
    // (gardées dans son seul navigateur) et les rayons les plus parcourus.
    var RAYONS_ACCUEIL = [
      ['helmet.integral', 'Casques intégraux'], ['helmet.jet', 'Casques jet'],
      ['helmet.modular', 'Casques modulables'], ['jacket', 'Blousons & vestes'],
      ['gloves', 'Gants'], ['boots', 'Bottes & chaussures'], ['pants', 'Pantalons']
    ];
    var CLE_RECENTES = 'mc-recherches-recentes';

    function recentes() {
      try { return JSON.parse(localStorage.getItem(CLE_RECENTES) || '[]').slice(0, 5); }
      catch (e) { return []; }
    }
    function retenir(texte) {
      texte = (texte || '').trim();
      if (texte.length < MINIMUM) return;
      try {
        var r = recentes().filter(function (t) { return t.toLowerCase() !== texte.toLowerCase(); });
        r.unshift(texte);
        localStorage.setItem(CLE_RECENTES, JSON.stringify(r.slice(0, 5)));
      } catch (e) { /* stockage refusé : on s'en passe */ }
    }

    function peindreAccueil() {
      liste.innerHTML = '';
      options = [];
      liste.classList.add('sugg--accueil');
      var r = recentes();
      if (r.length) {
        rubriqueDans(liste, 'Recherches récentes');
        r.forEach(function (t) {
          option('/recherche?q=' + encodeURIComponent(t), [elem('span', 'sugg__quoi', t)]);
        });
      }
      rubriqueDans(liste, 'Rayons les plus parcourus');
      var puces = elem('div', 'sugg__puces');
      liste.appendChild(puces);
      RAYONS_ACCUEIL.forEach(function (x) {
        var a = option('/c/' + x[0], [elem('span', '', x[1])], undefined, puces);
        a.classList.add('sugg__puce');
      });
      ouvrir();
    }

    // Sur ordinateur le panneau déborde le champ (860 px) : on le recale pour
    // qu'il tienne dans la fenêtre. Sur téléphone il prend l'écran sous la
    // barre ; on ne lui donne que la hauteur où commencer.
    function placer() {
      var r = form.getBoundingClientRect();
      if (window.matchMedia('(max-width: 760px)').matches) {
        liste.style.left = '';
        liste.style.setProperty('--sugg-haut', Math.round(r.bottom + 6) + 'px');
        return;
      }
      if (liste.classList.contains('sugg--accueil')) { liste.style.left = ''; return; }
      var large = Math.min(860, window.innerWidth - 32);
      var gauche = Math.max(16 - r.left, Math.min(0, window.innerWidth - 16 - large - r.left));
      liste.style.left = Math.round(gauche) + 'px';
    }

    function ouvrir() {
      placer();
      liste.hidden = false;
      champ.setAttribute('aria-expanded', 'true');
      surligner(-1);
    }

    form.addEventListener('submit', function () { retenir(champ.value); });
    liste.addEventListener('click', function (e) {
      if (e.target.closest('a') && champ.value.trim()) retenir(champ.value);
    });
    window.addEventListener('resize', function () { if (!liste.hidden) placer(); });

    function annuler() {
      if (encours) { encours.abort(); encours = null; }
    }

    function demander() {
      var texte = champ.value.trim();
      // Effacé sous le minimum : la requête partie pour « shoei » ne doit
      // pas rouvrir la liste une seconde plus tard (audit du 30/09/2026).
      if (texte.length < MINIMUM) {
        annuler();
        if (document.activeElement === champ && !texte) peindreAccueil(); else fermer();
        return;
      }
      annuler();
      encours = new AbortController();
      fetch('/api/suggestions?q=' + encodeURIComponent(texte),
            { signal: encours.signal })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          // seule la réponse au texte ENCORE affiché dans le champ se peint
          if (d && champ.value.trim() === texte) peindre(d, texte);
        })
        .catch(function () { /* annulée ou réseau : on laisse la liste en place */ });
    }

    champ.addEventListener('input', function () {
      clearTimeout(minuteur);
      minuteur = setTimeout(demander, ATTENTE);
    });

    champ.addEventListener('keydown', function (e) {
      if (liste.hidden) {
        if (e.key === 'ArrowDown') { demander(); }
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        surligner((choisi + 1) % options.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        surligner(choisi <= 0 ? options.length - 1 : choisi - 1);
      } else if (e.key === 'Enter') {
        // Entrée sans sélection lance la recherche normale : le formulaire fait
        // déjà ce qu'il faut, on ne s'interpose pas.
        if (choisi >= 0) { e.preventDefault(); options[choisi].click(); }
      } else if (e.key === 'Escape') {
        clearTimeout(minuteur);
        annuler();
        fermer();
      }
    });

    champ.addEventListener('focus', function () {
      if (champ.value.trim().length >= MINIMUM) demander();
      else if (!champ.value.trim()) peindreAccueil();
    });

    document.addEventListener('click', function (e) {
      if (!form.contains(e.target)) fermer();
    });
  }

  function demarrer() {
    document.querySelectorAll('form[role="search"]').forEach(installer);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', demarrer);
  } else {
    demarrer();
  }
})();
