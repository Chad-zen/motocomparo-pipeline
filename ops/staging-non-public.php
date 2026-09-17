<?php
/**
 * staging.motocomparo.com — fermer l'accès aux visiteurs anonymes.
 *
 * Le staging est une COPIE COMPLÈTE de la production (docs/infrastructure.md) :
 * même catalogue, même contenu, et les mêmes fuites. Constaté le 2026-09-14 :
 * `robots.txt` y interdit bien l'indexation, mais le site répond 200 à tout le
 * monde et son API REST publie l'identifiant du compte — comme le faisait la
 * production avant correction.
 *
 * Le mode « Bientôt disponible » de WooCommerce a été essayé et ne suffit pas :
 * le thème ReHub rend la page d'accueil hors des gabarits WooCommerce, donc le
 * garde-fou ne s'y applique pas. Vérifié de l'extérieur : 294 Ko de page et les
 * produits toujours visibles après activation.
 *
 * Celui-ci coupe à la racine, avant tout rendu.
 *
 * À COLLER DANS WPCode SUR LE STAGING (nouvel extrait PHP, « Run Everywhere »),
 * SANS la ligne `<?php`. Puis vider le cache LiteSpeed.
 *
 * Sortie de secours : si quelque chose tourne mal, WPCode se désactive depuis
 * l'administration, qui reste accessible — un administrateur connecté n'est
 * jamais bloqué.
 */

add_action('template_redirect', function () {
    // L'administration, les tâches planifiées et l'API interne continuent.
    if (is_user_logged_in() || is_admin() || wp_doing_cron()) {
        return;
    }
    // Laisser passer la page de connexion, sinon plus personne ne rentre.
    if (isset($GLOBALS['pagenow']) && in_array($GLOBALS['pagenow'],
            array('wp-login.php', 'wp-register.php'), true)) {
        return;
    }

    status_header(403);
    nocache_headers();
    header('X-Robots-Tag: noindex, nofollow', true);
    exit(
        '<!doctype html><html lang="fr"><meta charset="utf-8">'
        . '<meta name="viewport" content="width=device-width,initial-scale=1">'
        . '<title>Accès restreint</title>'
        . '<div style="font:16px/1.6 system-ui,sans-serif;max-width:32rem;'
        . 'margin:18vh auto;padding:0 1.5rem;text-align:center;color:#0f1524">'
        . '<h1 style="font-size:1.25rem">Environnement de préproduction</h1>'
        . '<p>Cet espace sert aux essais et n\'est pas ouvert au public.</p>'
        . '<p><a href="https://motocomparo.com/" style="color:#0f1524">'
        . 'Aller sur motocomparo.com</a></p></div>'
    );
}, 0);

// L'API REST des utilisateurs, par sécurité : si l'extrait ci-dessus était un
// jour désactivé, elle ne doit pas se remettre à publier l'identifiant.
add_filter('rest_endpoints', function ($endpoints) {
    if (is_user_logged_in()) {
        return $endpoints;
    }
    unset($endpoints['/wp/v2/users']);
    unset($endpoints['/wp/v2/users/(?P<id>[\d]+)']);
    return $endpoints;
});
