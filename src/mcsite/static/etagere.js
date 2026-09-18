/* Étagères qui bouclent.
   ==========================================================================

   Demandé par la propriétaire le 17/09/2026 : « scroll illimité avec un nombre
   de produits limités ». Autrement dit, on ne va pas chercher d'autres fiches
   au serveur — la sélection reste celle qu'on a choisie, six ou huit produits
   pertinents — mais l'étagère ne doit jamais buter sur un bord.

   Le principe : on duplique la série, et quand le défilement a parcouru une
   série entière on le ramène en arrière d'exactement cette longueur. Les
   pixels sous le doigt sont les mêmes avant et après le saut, donc rien ne se
   voit : ni à-coup, ni clignotement. C'est un tapis roulant, pas un
   chargement.

   Deux conditions pour que le saut soit invisible :

   1. Une série doit être AU MOINS aussi large que la fenêtre. Sinon le saut
      remplace une portion visible par une autre, et l'œil l'attrape. Quand la
      série est trop courte, on la répète d'abord autant de fois qu'il faut :
      c'est cette série épaissie qui devient l'unité de bouclage.
   2. Il faut deux exemplaires de cette unité, pas plus : on boucle entre 0 et
      une longueur d'unité.

   Les copies sont `aria-hidden` et sorties du parcours clavier : un lecteur
   d'écran et la touche Tab ne doivent traverser la sélection qu'une fois.
   Elles portent aussi `data-copie`, pour qu'un script qui compterait les
   fiches d'une étagère sache les écarter.
   ====================================================================== */

(function () {
  'use strict';

  var SELECTEURS = '.proches__grille, .rayon__piste';

  function gouttiere(piste) {
    var g = parseFloat(getComputedStyle(piste).columnGap);
    return isNaN(g) ? 0 : g;
  }

  function copier(modeles, piste) {
    modeles.forEach(function (el) {
      var copie = el.cloneNode(true);
      copie.setAttribute('aria-hidden', 'true');
      copie.setAttribute('tabindex', '-1');
      copie.dataset.copie = '1';
      // Un lien copié reste un lien : sans ça, Tab le saute mais un clic du
      // milieu ou un lecteur d'écran en mode navigation le trouve encore.
      copie.querySelectorAll('a, button, [tabindex]').forEach(function (f) {
        f.setAttribute('tabindex', '-1');
      });
      piste.appendChild(copie);
    });
  }

  function boucler(piste) {
    if (piste.dataset.boucle) return;
    // Un saut doit être instantané. Si une feuille de style passait un jour
    // l'étagère en défilement doux, le retour en arrière s'animerait sous les
    // yeux et toute l'illusion tomberait.
    piste.style.scrollBehavior = 'auto';

    var modeles = Array.prototype.slice.call(piste.children);
    if (!modeles.length) return;

    var gap = gouttiere(piste);
    // `scrollWidth` n'inclut pas la gouttière qui suivrait le dernier
    // élément ; on l'ajoute, sinon chaque tour perdrait 12 px et l'étagère
    // dériverait lentement vers la gauche.
    var serie = piste.scrollWidth + gap;
    var fenetre = piste.clientWidth;

    // Rien ne dépasse : une étagère qui tient à l'écran n'a pas à boucler.
    if (serie - gap <= fenetre + 8) return;

    // Condition 1 : épaissir la série jusqu'à couvrir la fenêtre.
    var repetitions = Math.max(1, Math.ceil(fenetre / serie));
    for (var i = 1; i < repetitions; i++) copier(modeles, piste);
    var unite = serie * repetitions;

    // Condition 2 : un deuxième exemplaire de l'unité, celui dans lequel on
    // retombe.
    var unUnite = Array.prototype.slice.call(piste.children);
    copier(unUnite, piste);

    piste.dataset.boucle = '1';
    commander(piste, serie / modeles.length, unite);

    var enCours = false;
    piste.addEventListener('scroll', function () {
      if (enCours) return;
      var x = piste.scrollLeft;
      var saut = 0;
      if (x >= unite) saut = -unite;
      else if (x <= 0) saut = unite;
      if (!saut) return;

      // Pas besoin de désactiver l'accrochage pendant le saut : l'unité vaut
      // un nombre ENTIER de pas (largeur d'une carte + gouttière), donc un
      // point d'accrochage retombe exactement sur un point d'accrochage. La
      // version d'avant éteignait puis rallumait `scroll-snap-type` dans le
      // même bloc synchrone — ce que le navigateur ne voit jamais, les styles
      // n'étant appliqués qu'en fin de tâche. C'était du code sans effet.
      enCours = true;
      piste.scrollLeft = x + saut;
      enCours = false;
    }, { passive: true });
  }

  /* --- Les commandes de l'étagère -----------------------------------------

     Avant : rien. L'étagère se déplaçait à la BARRE DE DÉFILEMENT NATIVE du
     système, posée sous chaque rangée avec ses deux petits triangles. Signalé
     par la propriétaire le 18/09/2026 — « vraiment old school » — et elle a
     raison : c'est un contrôle de fenêtre de 1995 sous une vitrine.

     Les boutons sont créés ICI et non dans le gabarit, pour trois raisons :

     1. sans JavaScript, ils ne serviraient à rien — mieux vaut qu'ils
        n'existent pas, le défilement natif reste possible au doigt et à la
        molette ;
     2. ils ne sont posés que sur les étagères qui DÉBORDENT vraiment ; une
        rangée qui tient à l'écran n'a rien à commander ;
     3. trois étagères dans le gabarit, plus celle des « déjà vus » insérée
        après coup : quatre copies du même balisage à tenir à jour.
  */
  function commander(piste, pas, unite) {
    // Sans pas fourni, on le mesure : largeur d'un enfant plus la gouttière.
    if (!pas) {
      var premier = piste.firstElementChild;
      if (!premier) return;
      pas = premier.getBoundingClientRect().width + gouttiere(piste);
    }
    if (pas < 1) return;
    if (piste.dataset.commande) return;
    piste.dataset.commande = '1';
    var cadre = document.createElement('div');
    cadre.className = 'piste-cadre';
    piste.parentNode.insertBefore(cadre, piste);
    cadre.appendChild(piste);

    [-1, 1].forEach(function (sens) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'piste__nav piste__nav--' + (sens < 0 ? 'gauche' : 'droite');
      b.setAttribute('aria-label',
        sens < 0 ? 'Voir les produits précédents' : 'Voir les produits suivants');
      b.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        + '<path d="' + (sens < 0 ? 'M15 5l-7 7 7 7' : 'M9 5l7 7-7 7')
        + '" fill="none" stroke="currentColor" stroke-width="2.2"'
        + ' stroke-linecap="round" stroke-linejoin="round"/></svg>';

      b.addEventListener('click', function () {
        // Un pas visible, pas une carte : on avance d'une fenêtre moins une
        // carte, pour qu'il reste un repère de ce qu'on vient de voir.
        var cartes = Math.max(1, Math.floor(piste.clientWidth / pas) - 1);
        var saut = cartes * pas * sens;

        // On franchit la couture AVANT d'animer, jamais pendant. Le bouclage
        // remet la position en arrière d'un coup ; si ça tombait au milieu
        // d'un défilement doux, l'animation serait coupée net et le bouton
        // paraîtrait ne pas marcher.
        if (unite) {
          var apres = piste.scrollLeft + saut;
          if (apres >= unite) piste.scrollLeft -= unite;
          else if (apres < 0) piste.scrollLeft += unite;
        }

        var doux = !window.matchMedia
          || !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        piste.scrollBy({ left: saut, behavior: doux ? 'smooth' : 'auto' });
      });
      cadre.appendChild(b);
    });
  }

  /* La bande de raccourcis de l'accueil défile elle aussi, et portait la même
     barre native — en haut de page, donc la plus visible de toutes.

     Elle ne BOUCLE pas, et c'est voulu : une liste de rayons a un début et une
     fin, un menu qui tourne en rond empêche de savoir si on a tout vu. Elle
     reçoit donc les commandes sans le tapis roulant. */
  function garnir() {
    document.querySelectorAll('.bande__piste').forEach(function (piste) {
      if (piste.scrollWidth <= piste.clientWidth + 8) return;
      commander(piste, 0, 0);
      var cadre = piste.parentNode;
      if (cadre && cadre.classList.contains('piste-cadre')) {
        cadre.classList.add('piste-cadre--bande');
      }
    });
  }

  function demarrer() {
    document.querySelectorAll(SELECTEURS).forEach(boucler);
    garnir();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', demarrer);
  } else {
    demarrer();
  }

  // L'étagère des « déjà vus » de l'accueil n'existe pas au chargement : elle
  // est cherchée en JavaScript et insérée ensuite. Sans cette veille elle
  // serait la seule à ne pas boucler — et c'est celle qu'on regarde le plus,
  // puisqu'elle ne contient que des fiches déjà visitées.
  if (window.MutationObserver) {
    new MutationObserver(function (lots) {
      for (var i = 0; i < lots.length; i++) {
        if (lots[i].addedNodes.length) { demarrer(); return; }
      }
    }).observe(document.body, { childList: true, subtree: true });
  }

  // Passer du portrait au paysage change la largeur de la fenêtre, donc la
  // condition 1. On ne reconstruit pas : l'unité reste plus large que la
  // fenêtre dans le sens qui compte, et reconstruire en cours de lecture
  // ferait sauter la position de l'étagère sous le doigt.
})();
