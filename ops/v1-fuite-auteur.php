<?php
/**
 * v1 — fermer la fuite de l'identifiant auteur sur motocomparo.com
 *
 * Constaté le 2026-09-14 sur le site en ligne : l'identifiant WordPress du
 * compte administrateur — un pseudo que WordPress dérive de l'adresse e-mail,
 * et d'où se lisaient donc un nom et une adresse Gmail — était servi
 * publiquement, sans authentification, par deux chemins :
 *
 *   /wp-json/wp/v2/users   -> le pseudo en clair
 *   /?author=1             -> redirection vers le pseudo
 *
 * La page auteur était déjà en `noindex` (Rank Math) et le nom affiché est
 * `contact@motocomparo.com` : le nom d'affichage n'a jamais été le problème.
 * Le problème est le pseudo, que WordPress dérive de l'identifiant de
 * CONNEXION. Le publier, c'est publier la moitié des accès.
 *
 * ÉTAT AU 2026-09-14 : les blocs 1 et 3 sont EN LIGNE (extrait WPCode
 * n° 258914, actif). Vérifié de l'extérieur : /wp-json/wp/v2/users répond
 * désormais 404. Restent le bloc 0 et la priorité du bloc 2, ci-dessous.
 *
 * POUR FINIR — 2 clics :
 *   WordPress > Extraits de code > « Securite — masquer l'identifiant auteur »
 *   Tout sélectionner dans l'éditeur, coller ce fichier SANS la ligne `<?php`,
 *   puis « Mettre à jour ». Enfin, vider le cache LiteSpeed (menu du haut).
 *
 * Le bloc 0 s'exécute UNE SEULE FOIS puis se désarme tout seul.
 * Il ne modifie ni l'identifiant de connexion, ni le mot de passe, ni l'e-mail,
 * ni un seul article : il ne renomme que le pseudo public.
 */

// 0. LA RACINE : renommer le pseudo lui-même. Tant qu'il contient un nom et une
//    adresse e-mail, chaque nouvelle porte le republiera. Garde par option :
//    s'exécute une fois, puis ne coûte plus rien.
add_action( 'init', function () {
	if ( 'fait' === get_option( 'mc_pseudo_auteur_anonymise' ) ) {
		return;
	}
	$u = get_user_by( 'id', 1 );
	if ( $u && 'motocomparo' !== $u->user_nicename ) {
		wp_update_user( array( 'ID' => 1, 'user_nicename' => 'motocomparo' ) );
	}
	update_option( 'mc_pseudo_auteur_anonymise', 'fait' );
} );

// 1. L'API REST ne répond plus sur les utilisateurs aux visiteurs non connectés.
//    Le test `is_user_logged_in()` garde l'éditeur de blocs fonctionnel en admin.
add_filter( 'rest_endpoints', function ( $endpoints ) {
	if ( is_user_logged_in() ) {
		return $endpoints;
	}
	unset( $endpoints['/wp/v2/users'] );
	unset( $endpoints['/wp/v2/users/(?P<id>[\d]+)'] );
	return $endpoints;
} );

// 2. `?author=N` ne trahit plus le pseudo : retour à l'accueil.
//    PRIORITÉ 0, et c'est tout le sujet : en priorité par défaut (10), la
//    redirection canonique de WordPress passe la première et publie le pseudo
//    avant que cette règle s'exécute. Mesuré le 2026-09-14 : la fuite subsistait.
add_action( 'template_redirect', function () {
	if ( ! is_admin() && ! is_user_logged_in() && isset( $_GET['author'] ) ) {
		wp_safe_redirect( home_url( '/' ), 301 );
		exit;
	}
}, 0 );

// 3. L'oEmbed publie aussi l'auteur et son URL quand une page est partagée.
add_filter( 'oembed_response_data', function ( $data ) {
	unset( $data['author_url'], $data['author_name'] );
	return $data;
} );
