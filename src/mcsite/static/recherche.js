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

    function rubrique(titre) {
      var t = elem('p', 'sugg__titre', titre);
      liste.appendChild(t);
    }

    function option(href, dedans, etiquette) {
      var a = elem('a', 'sugg__ligne');
      a.href = href;
      a.id = liste.id + '-o' + options.length;
      a.setAttribute('role', 'option');
      a.setAttribute('aria-selected', 'false');
      if (etiquette) a.setAttribute('aria-label', etiquette);
      dedans.forEach(function (n) { a.appendChild(n); });
      liste.appendChild(a);
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

    function peindre(d, texte) {
      liste.innerHTML = '';
      options = [];

      // UNE MARQUE TAPÉE SEULE : on propose la marque, pas trois de ses
      // produits pris au hasard.
      if (d.marque_seule) {
        var ms = d.marque_seule;
        rubrique('La marque');
        var nds = [];
        var vm = vignette(ms, 'sugg__grande');
        if (vm) nds.push(vm);
        var bm = elem('span', 'sugg__produit');
        bm.appendChild(elem('span', 'sugg__nom sugg__nom--grand',
          ms.marque.toUpperCase()));
        bm.appendChild(elem('span', 'sugg__marchands',
          'Voir les ' + ms.n + ' produits comparés'));
        nds.push(bm);
        var lm = option('/m/' + encodeURIComponent(ms.marque), nds,
          'Tous les produits ' + ms.marque.toUpperCase()
          + ', ' + ms.n + ' comparés');
        lm.classList.add('sugg__ligne--meilleur');
      }

      // LES MEILLEURS RÉSULTATS, en premier et en grand — plusieurs, pas un.
      // Six SZ-R ne diffèrent que par la finition : désigner un vainqueur, ce
      // serait cacher les autres réponses, aussi justes que lui.
      if (d.meilleurs && d.meilleurs.length) {
        rubrique(d.meilleurs.length > 1 ? 'Meilleurs résultats' : 'Meilleur résultat');
        d.meilleurs.forEach(function (m) {
          var noeuds = [];
          var v = vignette(m, 'sugg__grande');
          if (v) noeuds.push(v);
          var bloc = elem('span', 'sugg__produit');
          bloc.appendChild(elem('span', 'sugg__marque', m.marque));
          bloc.appendChild(elem('span', 'sugg__nom sugg__nom--grand', m.nom));
          // La couleur départage : trois SZ-R VAS EVO « SOLID » ne diffèrent
          // que par elle, et sans elle la liste montre trois fois la même
          // chose.
          var dessous = [];
          if (m.couleur) dessous.push(m.couleur);
          if (m.marchands) dessous.push(m.marchands + ' marchands comparés');
          if (dessous.length) {
            bloc.appendChild(elem('span', 'sugg__marchands', dessous.join(' · ')));
          }
          noeuds.push(bloc);
          if (m.prix !== null) {
            noeuds.push(elem('span', 'sugg__prix sugg__prix--grand',
              'dès ' + euros(m.prix)));
          }
          var ligne = option('/p/' + m.slug, noeuds,
            m.marque + ' ' + m.nom + (m.prix !== null ? ', dès ' + euros(m.prix) : ''));
          ligne.classList.add('sugg__ligne--meilleur');
        });
      }

      // L'ENTONNOIR EN PREMIER. C'est la proposition qui fait gagner le plus de
      // temps : elle répond à la fois « quelle marque » et « quel rayon ». La
      // mettre sous la liste des produits, c'est la cacher.
      if (d.entonnoir && d.entonnoir.length) {
        var marque = d.entonnoir[0].marque;
        rubrique(marque.toUpperCase() + ', par rayon');
        d.entonnoir.forEach(function (e) {
          // Le code de marque part TEL QU'IL EST STOCKE, en minuscules : le
          // filtre des listes compare a `brand_code` sans tenir compte de la
          // casse nulle part. Envoye en majuscules, le lien repondait 200 avec
          // zero produit — la pire des pannes, celle qui ressemble a un rayon
          // vide plutot qu'a une erreur.
          option('/c/' + e.rayon_code + '?marque=' + encodeURIComponent(marque),
            [elem('span', 'sugg__quoi', e.rayon),
             elem('span', 'sugg__compte', e.n)],
            marque.toUpperCase() + ' dans ' + e.rayon + ', ' + e.n + ' produits');
        });
      }

      var autres = (d.marques || []).filter(function (m) {
        // Même garde qu'au bloc au-dessus : si l'API omettait un jour
        // `entonnoir`, lire `.length` sur `undefined` levait une exception ici
        // et vidait TOUT l'affichage des suggestions — marques, rayons et
        // produits compris — pas seulement cette rubrique.
        return !(d.entonnoir && d.entonnoir.length) || m.marque !== d.entonnoir[0].marque;
      });
      if (autres.length) {
        rubrique('Marques');
        autres.forEach(function (m) {
          option('/m/' + encodeURIComponent(m.marque),
            [elem('span', 'sugg__quoi', m.marque.toUpperCase()),
             elem('span', 'sugg__compte', m.n)]);
        });
      }

      if (d.rayons && d.rayons.length) {
        rubrique('Rayons');
        d.rayons.forEach(function (r) {
          option('/c/' + r.code, [elem('span', 'sugg__quoi', r.label)]);
        });
      }

      if (d.produits && d.produits.length) {
        // `d.meilleurs` est déjà testé plus haut avant d'être parcouru ; ici
        // on relisait `.length` sans le même filet.
        rubrique(d.marque_seule ? 'Quelques produits'
                 : ((d.meilleurs && d.meilleurs.length) ? 'Autres produits' : 'Produits'));
        d.produits.forEach(function (p) {
          // Un comparateur d'équipement se lit à l'image autant qu'au texte :
          // « Casque intégral Arai CONCEPT-XE » ne dit rien de la couleur ni de
          // la forme, et trois lignes du même modèle se ressemblent toutes tant
          // qu'on ne les voit pas.
          var noeuds = [];
          var vign = vignette(p, 'sugg__vignette');
          if (vign) noeuds.push(vign);

          var corps = elem('span', 'sugg__produit');
          corps.appendChild(elem('span', 'sugg__marque', p.marque));
          corps.appendChild(elem('span', 'sugg__nom',
            p.couleur ? p.nom + ' — ' + p.couleur : p.nom));
          noeuds.push(corps);
          if (p.prix !== null) {
            noeuds.push(elem('span', 'sugg__prix', 'dès ' + euros(p.prix)));
          }
          option('/p/' + p.slug, noeuds,
            p.marque + ' ' + p.nom + (p.prix !== null ? ', dès ' + euros(p.prix) : ''));
        });
      }

      // Toujours une sortie vers la recherche complète : la liste ne montre que
      // les premiers résultats, et quelqu'un qui n'y trouve pas son bonheur ne
      // doit pas croire qu'il n'y a rien.
      if (options.length) {
        var tout = option('/recherche?q=' + encodeURIComponent(texte),
          [elem('span', 'sugg__tout', 'Voir tous les résultats pour « ' + texte + ' »')]);
        tout.classList.add('sugg__ligne--tout');
      }

      if (!options.length) { fermer(); dit.textContent = ''; return; }

      liste.hidden = false;
      champ.setAttribute('aria-expanded', 'true');
      surligner(-1);
      dit.textContent = options.length + ' proposition'
        + (options.length > 1 ? 's' : '');
    }

    function demander() {
      var texte = champ.value.trim();
      if (texte.length < MINIMUM) { fermer(); return; }
      if (encours) encours.abort();
      encours = new AbortController();
      fetch('/api/suggestions?q=' + encodeURIComponent(texte),
            { signal: encours.signal })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d) peindre(d, texte); })
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
        fermer();
      }
    });

    champ.addEventListener('focus', function () {
      if (champ.value.trim().length >= MINIMUM) demander();
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
