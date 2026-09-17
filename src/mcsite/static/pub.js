/* La rotation des bannières partenaires.
   ==========================================================================

   Le tirage se fait ICI, dans le navigateur, et pas côté serveur : nginx garde
   chaque page une heure, si bien qu'un tirage au serveur figerait une bannière
   par page pour toute cette durée — un marchand aurait l'accueil, un autre les
   casques, et plus rien ne tournerait.

   Une seule image est chargée, celle qui est montrée. Les cinq adresses sont
   dans l'attribut, mais quatre ne partent jamais sur le réseau.

   Si l'image ne se charge pas — marchand en maintenance, bloqueur de publicité,
   réseau coupé — l'emplacement se retire au lieu de laisser un rectangle vide
   de 250 px au milieu de la page.
   ====================================================================== */

(function () {
  'use strict';

  function poser(bloc) {
    var liste;
    try {
      liste = JSON.parse(bloc.dataset.partenaires || '[]');
    } catch (e) {
      bloc.hidden = true;
      return;
    }
    if (!liste.length) { bloc.hidden = true; return; }

    var cadre = bloc.querySelector('[data-pub-cadre]');
    if (!cadre) return;

    var p = liste[Math.floor(Math.random() * liste.length)];

    var img = document.createElement('img');
    // `loading` en `eager` : l'emplacement est en bas de page, donc déjà proche
    // du regard quand on y arrive. En `lazy`, la bannière se chargeait au
    // moment précis où le visiteur la regardait, et il voyait le trou.
    img.loading = 'eager';
    img.alt = 'Publicité ' + (p.nom || '');
    img.addEventListener('error', function () { bloc.hidden = true; });
    img.src = p.image;

    var a = document.createElement('a');
    a.href = p.clic;
    a.target = '_blank';
    // `sponsored` dit aux moteurs ce que la mention dit aux visiteurs ; sans
    // lui, un lien rémunéré non déclaré est une faute aux yeux de Google comme
    // de la loi. `noopener` empêche la page ouverte de manipuler la nôtre.
    a.rel = 'nofollow sponsored noopener';
    a.setAttribute('aria-label',
      'Publicité — voir le site de ' + (p.nom || 'notre partenaire') + ' (nouvel onglet)');
    a.appendChild(img);

    cadre.appendChild(a);
  }

  function demarrer() {
    document.querySelectorAll('[data-pub]').forEach(poser);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', demarrer);
  } else {
    demarrer();
  }
})();
