/* Page « À propos » : des animations sobres (20/10/2026).

   - les trois chiffres comptent jusqu'à leur valeur quand ils entrent à l'écran ;
   - les cartes et les étapes apparaissent l'une après l'autre au défilement ;
   - rien ne bouge pour qui a demandé « moins d'animation » dans son système, et rien ne manque si ce
     script ne se charge pas : le contenu est dans le HTML, visible, avec ses chiffres définitifs.

   Les éléments ne sont cachés QUE par ce script (classe `reveal` ajoutée ici) : sans lui, la page est
   complète. */
(function () {
  'use strict';
  var calme = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (calme || !('IntersectionObserver' in window)) return;

  var nombre = new Intl.NumberFormat('fr-FR');

  /* --- 1. les chiffres qui comptent ------------------------------------ */
  function compter(el) {
    var cible = parseInt(el.getAttribute('data-compte'), 10);
    if (!cible || isNaN(cible)) return;
    var prefixe = el.getAttribute('data-prefixe') || '';
    var duree = 1300;
    var debut = null;
    function pas(t) {
      if (debut === null) debut = t;
      var x = Math.min(1, (t - debut) / duree);
      var v = Math.round(cible * (1 - Math.pow(1 - x, 3)));      /* ralentit vers la fin */
      el.textContent = prefixe + nombre.format(v).replace(/\s/g, ' ');
      if (x < 1) requestAnimationFrame(pas);
    }
    el.textContent = prefixe + '0';
    requestAnimationFrame(pas);
  }

  /* --- 2. l'apparition au défilement ----------------------------------- */
  var cibles = [];
  document.querySelectorAll('.apropos__cartes article, .apropos__etapes li, .apropos__chiffres li, .apropos__etapes h2, .apropos__piliers h2')
    .forEach(function (el, i) {
      el.classList.add('reveal');
      cibles.push(el);
    });

  var vus = 0;
  var obs = new IntersectionObserver(function (entrees) {
    entrees.forEach(function (e) {
      if (!e.isIntersecting) return;
      var el = e.target;
      obs.unobserve(el);
      /* petit décalage entre frères : « une, puis la suivante » */
      var frere = Array.prototype.indexOf.call(el.parentNode.children, el);
      el.style.transitionDelay = (Math.min(frere, 5) * 90) + 'ms';
      el.classList.add('est-visible');
      var n = el.querySelector('[data-compte]');
      if (n) compter(n);
    });
  }, { threshold: 0.18, rootMargin: '0px 0px -6% 0px' });

  cibles.forEach(function (el) { obs.observe(el); });
})();
