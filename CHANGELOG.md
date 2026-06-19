# Changelog

## [1.17.5] - 2026-06-19

### Corrections de bugs

- **Modales Non-Intrusives (G-08)** : Remplacement de l'utilisation de `window.confirm` par une modale de confirmation inline lors de l'annulation d'une manche FFA.
- **Robustesse des tests unitaires** : Correction des tests unitaires i18n suite à l'introduction de la séparation des répertoires de traduction en environnement de production et de données utilisateur.

## [1.17.4] - 2026-06-19

### Corrections de bugs

- **Persistance des illustrations de jeux (Docker)** : Les images de couverture des jeux étaient stockées dans un dossier éphémère du conteneur (`/app/static/uploads/games/`) et disparaissaient à chaque redémarrage ou mise à jour Docker. Elles sont désormais stockées dans le volume persistant `/app/data/game_images/`. Une migration automatique au démarrage déplace les fichiers existants et met à jour les chemins en base de données.

### Maintenance

- **Nettoyage de sécurité pour la release** : Retrait des fichiers `.bak` du dépôt Git, ajout de `test_api.py` et `*.bak` au `.gitignore` pour éviter l'inclusion de fichiers de développement ou de sauvegarde dans les releases publiques.

## [1.17.3] - 2026-06-19

### Améliorations & Corrections de bugs

- **Mutualisation de la modale d'édition des tournois** : Création d'un composant unique réutilisable `EditTournamentModal.svelte` et suppression de la duplication de code entre les pages tournois joueurs et administration.
- **Correction sur le Plan de Salle** : Résolution d'un bug d'affichage qui affichait l'expression ternaire JavaScript brute au lieu de la traduction dynamique correcte lorsque le joueur n'avait pas de siège. Simplification et uniformisation des instructions de navigation en "Clic pour naviguer." dans les langues supportées.
- **Traduction de la page Assistant IA** : Extraction et localisation des 14 phrases de chargement gauloises et du titre par défaut des conversations dans les fichiers i18n (`fr.json`, `en.json`, `es.json`) ; mise à jour du backend pour supporter les détections d'auto-titre sur les titres par défaut traduits.
- **Redimensionnement dynamique et cohérent de la Sidebar** : Détection automatique en JavaScript du retour à la ligne des libellés de navigation de la barre latérale, avec réduction uniforme de la taille de police (jusqu'à `0.75rem`) pour éviter les retours à la ligne inesthétiques tout en conservant une cohérence visuelle parfaite.

## [1.17.2] - 2026-06-19

### Corrections de bugs & Internationalisation (i18n)

- **Résolution du mix de langues (français/espagnol)** : Remplacement de tous les textes codés en dur en français par des appels réactifs `$t(...)` dans le composant de gestion des tournois.
- **Support complet de la pluralisation espagnole** : Correction dynamique du suffixe de pluriel pour "Jugador" (qui passait de "Jugador" à "Jugadors") pour afficher correctement "Jugadores" en espagnol en fonction du store de langue active (`currentLang`).
- **Synchronisation globale des fichiers de langues** : Mise à jour et alignement des clés manquantes dans `fr.json`, `en.json` et `es.json` tant dans la configuration d'usine (`static/i18n`) que dans les surcharges utilisateur (`data/i18n`).

## [1.17.1] - 2026-06-18

### Nouvelles fonctionnalités

- **Seeding automatique des fichiers de langue au démarrage** : Copie automatique des fichiers d'usine (`fr.json`, `en.json`, `es.json` complet) dans le dossier de données de l'utilisateur (`data/i18n/`) s'ils n'existent pas encore, pour faciliter la prise en main et la personnalisation par l'utilisateur.

### Corrections de bugs

- **Chargement dynamique des langues modifiées** : Correction de l'application Svelte pour charger dynamiquement les fichiers i18n depuis l'API de fusion `/api/i18n/{lang}` au lieu de `/static/i18n/`, permettant de prendre en compte immédiatement les modifications locales ou de nouvelles langues (comme l'espagnol).
- **Ajustement de la hauteur d'affichage (Viewport Scroll)** : Correction de la hauteur des conteneurs pour éliminer les barres de défilement externes indésirables sur la page d'administration des langues en forçant `.container` et `.lang-page` à 100% de la hauteur disponible.
- **Sécurité et filtrage des langues** : Interdiction d'utiliser ou de l'ister les routes réservées de l'API (comme `bulk-translate` ou `auto-translate`) comme codes de langue valides et suppression des fichiers correspondants.

## [1.17.0] - 2026-06-18

### Nouvelles fonctionnalités

- **Système d'internationalisation complet (i18n)** — Mise en place d'une architecture multilingue intégrale pour l'application :
  - **Store réactif Svelte** (`i18nStore.ts`) : Chargement asynchrone des traductions depuis l'API, sélection de la langue avec persistance `localStorage`, helper `$t()` avec interpolation de variables (`{name}`, `{count}`), et mapping des drapeaux par code langue.
  - **Backend i18n** (`/api/i18n`) : Endpoints CRUD complets pour la gestion des langues (GET, POST, PUT, DELETE), avec système de merge bicouche (`static/i18n/` ← fichiers livrés, `data/i18n/` ← éditions utilisateur).
  - **Traduction automatique par IA** : Endpoint dédié utilisant la file Ollama pour traduire les clés i18n d'une langue source vers une langue cible, avec nettoyage automatique du markdown et des guillemets parasites.
  - **Fichiers de langue** : `fr.json` (850+ clés), `en.json` (traduction complète), support de nouvelles langues (ex: `es.json`).
- **Page d'administration des langues** (`/dashboard/admin/languages`) — Interface complète de gestion des traductions :
  - **Éditeur bicolonne** : Vue côté-à-côté de la langue de référence et de la langue cible, avec catégorisation automatique par préfixe de clé (Sidebar, Dashboard, Tournois, IA, etc.).
  - **Navigation par catégories** : Barre latérale avec compteurs de clés manquantes par catégorie et badge de progression.
  - **Traduction individuelle & en masse** : Bouton de traduction IA par clé, traduction en lot (toutes les clés ou seulement les vides), avec barre de progression et bouton d'annulation.
  - **Recherche et filtrage** : Recherche instantanée dans les clés, valeurs source et cible.
  - **Persistance des catégories repliées** : L'état de collapse des catégories est sauvegardé en `localStorage`.
  - **Toasts de confirmation** : Feedback visuel pour toutes les actions (sauvegarde, suppression, synchronisation, traduction).
  - **Modales de confirmation inline** : Confirmations de suppression de langue via popover sous le bouton (sans titre, Valider/Annuler) avec fond opaque, conformément aux règles du projet.
- **Synchronisation des clés manquantes** — Détection et ajout automatique des clés absentes d'un fichier de langue par rapport à la référence (`fr.json`) :
  - **Distinction clés absentes vs non-traduites** : Nouveau compteur `structuralMissingCount` différenciant les clés manquantes du fichier (🔑 rouge) des clés présentes mais vides (⚠️ orange).
  - **Bandeau d'alerte** : Notification visuelle rouge lorsque des clés structurelles sont manquantes (typiquement après une mise à jour de l'app), avec explication et bouton de synchronisation intégré.
  - **Endpoint `/api/i18n/{lang}/sync`** : Ajout des clés manquantes avec valeurs vides, retour du nombre de clés ajoutées.
- **Optimisation i18n — Regroupement des doublons** : Factorisation des clés de traduction dupliquées pour réduire la taille des fichiers de langue.
- **Sélecteur de langue dans le menu** : Nouveau dropdown de sélection de la langue dans la barre latérale du dashboard, avec drapeaux emoji et persistance du choix.

### Corrections de bugs

- **Accès aux boutons inline après blocage IA** : Correction d'un bug permettant aux joueurs bloqués par l'IA de continuer à accéder aux boutons d'action dans les conversations.
- **Synchronisation des clés ES** : Correction du backend qui retournait une erreur 404 pour les langues avec un fichier vide (`{}` est falsy en Python). La condition a été corrigée de `not target_data` à `target_data is None`.
- **Prompt de tournois localisé** : Déplacement du prompt système IA des tournois dans les fichiers i18n pour permettre sa traduction.
- **Éditeur d'image de profil** : Correction de la sauvegarde du crop/zoom/couleur de fond et réouverture du modal à l'édition au lieu d'un prompt de fichier.

## [1.16.2] - 2026-06-14

### Corrections de bugs

- **Historique des versions (Docker Hub / Unraid)** : Correction de la séquence de copie dans le `Dockerfile.standalone` qui provoquait l'écrasement du `CHANGELOG.md` par un fichier vide temporaire lors de la génération de l'image de production.

## [1.16.1] - 2026-06-14

### Corrections de bugs & Résilience

- **Résilience de démarrage (Redirect Loop)** : Résolution d'une boucle infinie de redirection clignotante entre la page de connexion et le tableau de bord en cas de serveur injoignable, hors ligne ou en cours de redémarrage.
- **Écran de chargement unifié** : La page de connexion reste sur l'écran de chargement avec le logo animé tant que la vérification de session n'est pas finalisée, évitant tout clignotement ou affichage prématuré du formulaire.
- **Retry automatique & Manuel** : Ajout d'une relance automatique de connexion toutes les 3 secondes en cas de défaillance réseau, accompagnée d'un bouton de tentative manuelle "🔄 RÉESSAYER".

## [1.16.0] - 2026-06-14

### Nouvelles fonctionnalités & Améliorations

- **Éditeur d'Avatar Visuel (Canvas)** : Ajout d'une interface modale interactive à l'importation de l'image de l'avatar (zoom 0.5x à 4x, et recadrage/déplacement par glisser-déposer sur PC et mobile).
- **Couleur de fond personnalisée** : Option de choix d'une couleur de fond (Transparent, Blanc, Noir, Bleu Alanbix, Sombre ou Couleur personnalisée via un color picker) pour remplir les parties transparentes des images PNG à l'importation.
- **Sélecteur de format d'affichage** : Option permettant de choisir le format de rendu de l'avatar (Cercle, Carré arrondi, Carré pur) enregistré en base de données.
- **Propagation globale du masque d'avatar** : La forme de l'avatar choisie par chaque joueur est répercutée partout où son icône est affichée (Sidebar, Dashboard Leaderboard, Trophées de profil, Messagerie instantanée, Chat IA, Brackets de Tournois, Plan de salle 2D et Mode Projecteur public).
- **Optimisations de performances** : Remplacement des filtres de flou lourds (`backdrop-filter`) par un assombrissement opaque (`rgba(0, 0, 0, 0.9)`) pour économiser les ressources processeur des utilisateurs.
- **Ergonomie** : Blocage automatique de la sélection de texte durant le déplacement de l'image de l'avatar pour éviter les comportements confus.
- **Plan de salle optimisé** : Réduction légère de la taille des icônes d'avatars de la carte 2D (de 22px à 18px) pour conserver l'affichage du nom de l'équipe même lorsqu'un avatar est présent.

## [1.15.5] - 2026-06-06

### Corrections de bugs

- **Synchronisation des versions** : Alignement complet des numéros de version (v1.15.5) entre le code (package.json), le fichier système et l'affichage de l'interface.
- **Affichage des notes de mise à jour (Unraid)** : Correction du `Dockerfile` qui ne copiait pas les fichiers métadonnées, empêchant la lecture du CHANGELOG dans l'image de production unifiée.


## [1.15.4] - 2026-06-06

### Nouvelles fonctionnalités & Améliorations

- **Redimensionnement du chat (Joueurs)** : Ajout d'une barre de redimensionnement permettant d'élargir le panneau de conversation jusqu'à 70% de la largeur de l'écran. L'ajustement est sauvegardé de manière persistante.
- **Animation de l'écran de chargement** : Ajout d'une animation dynamique de "distillation" (logo incliné, bulles, effet de pulsation) sur l'écran de chargement principal.
- **Interface Admin (IA)** : Augmentation de la taille des champs de saisie pour les prompts de l'IA. La hauteur des encarts s'ajuste désormais parfaitement entre les différentes colonnes.

### Corrections de bugs

- **Arbres de tournois** : Désactivation de la sélection de texte lors du glisser-déposer à la souris pour éviter les comportements inattendus lors du déplacement sur la page.
- **Affichage des dates (TimeAgo)** : Correction du calcul du décalage horaire pour les notifications et les messages de discussion. Les dates retournées par le serveur sont maintenant correctement interprétées en UTC afin de refléter l'heure locale exacte de l'utilisateur.


## [1.15.3] - 2026-06-06

### Nouvelles fonctionnalités

- **Suivi et notifications des réponses IA / Admin pour le joueur** :
  - **Badge sur le lien de navigation** : Un compteur rouge s'affiche à côté de l'onglet « Assistant IA » dans la barre latérale pour notifier le joueur lorsqu'une réponse de l'IA (ou une intervention d'un administrateur) est reçue s'il se trouve sur une autre page.
  - **Highlight et badge Nouveau en temps réel** : Dans l'interface de l'IA, les conversations contenant des réponses non lues sont mises en évidence par une bordure verte et un badge « Nouveau ».
  - **Gestion en temps réel** : La mise à jour s'effectue instantanément via WebSocket (aucun F5 requis), et l'état lu est réinitialisé dès que le joueur sélectionne ou charge la conversation concernée.
  - **Pas de doublons** : L'envoi d'un message par l'admin n'affiche plus de double toast (la notification système se chargeant du message classique).

## [1.15.2] - 2026-06-06

### Corrections de bugs

- **Badges non lus en temps réel (Admin - Conversations IA)** :
  - **Aucun F5 nécessaire** : Les badges « Nouveau » et le compteur de l'onglet « Conversations IA » se mettent à jour en temps réel via WebSocket, sans rechargement de page.
  - **Disparition immédiate au clic** : Le badge vert et le highlight d'une conversation disparaissent instantanément quand l'administrateur clique dessus (mise à jour optimiste locale avant l'appel API).
  - **Anti-réintroduction** : `loadAdminConversations()` préserve maintenant l'état lu de la conversation active, empêchant le serveur de réintroduire le badge après un rafraîchissement de liste.
  - **Distinction user vs bot** : Le backend envoie maintenant un champ `role` dans les événements WebSocket `chat_updated` ; seuls les messages de rôle `user` incrémentent le compteur non lu pour l'administrateur (pas les réponses de l'IA).
  - **Badge dès le chargement** : Le badge de l'onglet « Conversations IA » est calculé dès le chargement de la page d'administration, sans avoir à cliquer sur l'onglet.

## [1.15.1] - 2026-06-06

### Nouvelles fonctionnalités

- **Compteur et suivi des messages non lus (Administration - Conversations IA)** :
  - **Badge sur l'onglet** : Affichage dynamique du nombre total de messages non lus par l'administrateur à côté de l'intitulé d'onglet "Conversations IA".
  - **Détails par discussion** : Indication du nombre exact de nouveaux messages non lus (ex: `2 nouveaux`) sur chaque carte de conversation de la liste latérale.
  - **Highlight dynamique** : Conservation de la bordure verte d'accentuation sur les conversations tant que l'administrateur ne les a pas lue.
  - **Marquage comme lu automatique** : Une conversation est automatiquement marquée comme lue au moment où l'administrateur clique pour l'ouvrir.

## [1.15.0] - 2026-06-06

### Nouvelles fonctionnalités

- **Modale de statistiques des joueurs (Leaderboard)** -- Clic sur un joueur dans le leaderboard (ou dans la liste des membres d'une équipe) ouvre une modale opaque affichant ses statistiques détaillées :
  - **Résumé des stats** : Points totaux accumulés, nombre de participations à des tournois et nombre de trophées remportés.
  - **Tournois & Inscriptions** : Liste des tournois auxquels le joueur participe ou est inscrit, avec badge d'état (`INSCRIT`, `EN COURS`, `TERMINE`), rang final, et répartition détaillée des points (participation, placement, score/bonus).
  - **Trophées & Distinctions** : Liste des récompenses spéciales (awards) décernées au joueur.
- **Amélioration du monitoring de l'onglet "Conversations IA" (Administration)** -- Ajout d'indicateurs d'état et d'activité des conversations pour les administrateurs :
  - **Dernière activité & Tri** : Affichage de la date et de l'heure du dernier message avec tri automatique par ordre de récurrence (récentes en premier).
  - **Aperçu du dernier message** : Affichage d'un court extrait du dernier message précédé de l'icône de l'auteur dans la liste latérale.
  - **Badge de nouveau message** : Un badge `Nouveau` et une bordure verte distincte s'affichent sur les conversations en attente de réponse (dernier message envoyé par le joueur).
  - **Détails d'exécution de l'IA (Métadonnées)** : Affichage du modèle/instance utilisé, du temps de réponse en secondes (`⏱️`) et des outils exécutés (`🛠️`) sous chaque réponse du bot.
  - **Horodatage complet** : Horodatage précis au format `JJ/MM/AAAA HH:MM:SS` pour chaque message dans la vue détaillée.

### Corrections de bugs

- **Suppression du flash du Dashboard pour les sessions expirées** -- Implémentation d'un écran de chargement translucide pendant la vérification d'authentification (`api.get('/me')`) au chargement du layout principal du dashboard. Cela empêche l'affichage transitoire du menu d'administration et du dashboard avant la redirection vers la page de connexion lorsque la session a expiré.
- **Modale de gestion du contexte opaque** -- Ajout d'un fond opaque (`var(--bg-secondary) !important`) sur la modale `.modal-content` de l'assistant IA, empêchant la discussion en arrière-plan d'apparaître par transparence et garantissant une lisibilité parfaite des options de compression.

---

## [1.13.0] - 2026-05-22

### Nouvelles fonctionnalites

- **Notifications de Prix Différées & Bouton de Diffusion** -- Les notifications ne sont plus envoyées immédiatement aux joueurs lors du calcul automatique ou de la mise à jour des prix. Un bouton dédié **📢 Diffuser les Prix aux Joueurs** a été ajouté sur la page d'administration centrale pour permettre aux organisateurs de contrôler précisément le moment de l'annonce officielle (par exemple, lors de la cérémonie de clôture de la LAN).
- **Endpoint de Notification Groupée** -- Implémentation de `POST /admin/awards/notify` pour créer toutes les notifications et diffuser les événements WebSocket en une seule fois, incluant une vérification de doublons pour éviter les renvois multiples involontaires.

---

## [1.12.0] - 2026-05-22

### Nouvelles fonctionnalites

- **Systeme de Prix Statistiques Automatiques** -- Transition complete vers un pipeline 100% stats-driven et automatise pour les prix de fin de LAN. Les 12 categories de distinctions (Premier de la LAN, Loup Solitaire, Marathonien, Bourreau, etc.) sont dorenavant calculees en temps reel d'apres les brackets de jeu.
- **Personnalisation & Templates de Prix** -- Interface d'administration entierement revue permettant de modifier en direct les titres et descriptions de chaque categorie, avec support des variables dynamiques d'interpolation (ex: `{points}`, `{wins}`). Option de restauration simple des textes par defaut.
- **Integration et Declenchement Automatique** -- Synchronisation automatique complete lors de la cloture (close) ou de la reouverture (reopen) de tournois, assurant que les notifications en temps reel (trophees remportes) sont instantanement transmises aux joueurs concernes en cas de changement de recipiendaire.

---

## [1.11.0] - 2026-05-22

### Nouvelles fonctionnalites

- **Systeme de Prix & Distinctions (Prix de fin de LAN) (AXE-43)** -- Ajout d'un systeme complet permettant aux administrateurs de decerner des prix classiques ou humoristiques a la fin de l'evenement.
- **Moteur de Suggestions Statistiques** -- Algorithme automatique analysant les brackets pour suggerer 12 distinctions differentes basees sur les performances reelles des joueurs (Meilleur joueur, Meilleure equipe, Loup solitaire, Marathonien, Passoire, Survivant du LB, L'Important c'est de participer, etc.).
- **Notifications & Profils** -- Creation de notifications temps reel de type "award" (icone 🎁) et affichage anime des trophees remportes sur la page de profil et dans l'historique des points des joueurs.
- **Purge de la base de donnees** -- Option de purge globale des prix et distinctions ajoutee dans la Zone de Danger de la page d'administration.

---

## [1.10.0] - 2026-05-22

### Nouvelles fonctionnalites

- **Barre de progression discrete & Chronometre (AXE-41)** -- Integration visuelle de la progression dans la couleur de fond des bulles du chat, avec affichage en haut a gauche du temps de reponse calcule a partir du Time to First Token (TTFT) pour une meilleure precision.
- **Persistance des statistiques par instance** -- Sauvegarde permanente des deques de durees moyennes par instance Ollama en base de donnees via la configuration systeme, avec affichage des badges de performance dans l'onglet des instances d'administration.
- **Outil d'auto-moderation IA (Anti-abus) (AXE-42)** -- Ajout de l'outil `block_user_from_ia` permettant a l'IA de bloquer de sa propre initiative les utilisateurs abusifs ou grossiers (tout en exemptant automatiquement les comptes administrateurs de cette sanction).
- **XML Fallback pour l'appel d'outils** -- Developpement d'un parser robuste d'extraction et d'execution d'outils base sur des balises XML de secours `<tool_call>`, rendant le support des outils tiers pleinement fonctionnel sur les modeles comme DeepSeek-R1 ou les petits modeles ne supportant pas Ollama tool-calling nativement.
- **Autofocus automatique** -- Focus automatique du champ de texte du chat des la fin de la generation ou lors du changement de salon de discussion.

### Ameliorations

- **Option auto-moderation** -- Toggle d'activation granularise ("Auto-moderation (Anti-abus)") integre dans les parametres IA de l'Administration pour rendre l'outil optionnel.
- **Robustesse du temps de reponse** -- Pause du chronometre de progression et soustraction automatique de la duree d'execution des outils pour ne pas fausser les statistiques de latence de l'IA.

---

## [1.9.2] - 2026-05-22

### Nouvelles fonctionnalites

- **Persistance des metadonnees IA (modele, instance, outils)** -- Les badges d'information (modele utilise, instance GPU, outils executes) restent desormais affiches de maniere permanente sur chaque message bot, meme apres rechargement de la page. Colonne `meta` JSON ajoutee en base de donnees et rendue via les endpoints API.
- **Saisie multiligne du prompt IA** -- Support de `Shift+Entree` dans le champ de saisie de l'assistant pour composer des messages sur plusieurs lignes sans envoyer.

### Ameliorations

- **Administration : refactoring de l'interface** -- Amelioration generale de la page d'administration (structure, lisibilite, organisation des sections).

---

## [1.9.1] - 2026-05-19

### Nouvelles fonctionnalites

- **Mises a jour en temps reel du dashboard Admin** -- Le tableau de bord administrateur se rafraichit automatiquement via WebSockets lors d'evenements systeme (tournois, joueurs, etc.).

### Corrections de bugs

- **Calcul du leaderboard en temps reel** -- Utilisation de `_compute_projected_standings` partage pour calculer les points en direct y compris pour les tournois FFA en cours.
- **Correction route async `update_ia_config`** -- Correction de l'import relatif de `ia_queue` et passage du handler en `async` pour supporter `asyncio.create_task`.

---

## [1.9.0] - 2026-05-19

### Nouvelles fonctionnalites

- **Decoupage RAG intelligent** -- Amelioration du chunking de la base de connaissances IA pour un meilleur contexte de reponse.
- **Chat admin en direct** -- Les administrateurs peuvent intervenir en temps reel dans les conversations IA des utilisateurs.
- **Editeur de base de connaissances** -- Interface d'edition/suppression des entrees de la Knowledge Base directement depuis l'administration.
- **Auto-titre asynchrone** -- Generation du titre de conversation IA de maniere non bloquante.

### Corrections de bugs

- **Correction BYE en brackets** -- Gestion correcte des BYE dans les tournois a elimination directe lorsque le nombre de participants n'est pas une puissance de 2.

---

## [1.8.1] - 2026-05-19

### Corrections de bugs

- **Classement championnat ex-aequo** -- Correction du tri des joueurs a egalite de points au demarrage d'un tournoi.
- **UI booleenne checkbox** -- Amelioration des checkboxes de mode booleen (V/D) dans l'interface de scoring.

---

## [1.8.0] - 2026-05-19

### Nouvelles fonctionnalites

- **Defilement automatique intelligent (Smart Scroll) (AXE-37)** : Defilement automatique du Chat IA pendant la generation, avec desactivation automatique si l'utilisateur scrolle vers le haut manuellement et reactivation lorsqu'il revient au bas du chat.
- **Indicateur d'Etat & Pensee du LLM (AXE-38)** : Rendu reactif en temps reel de la progression du modele (file d'attente, reflexion, appel d'outil, generation) avec affichage du cheminement de pensee (`<think>`) collapsible.
- **Outils de Diagnostic LAN/Reseau & Regles de Jeux (AXE-39)** : Nouveaux outils IA (`ping_host`, `traceroute_host`, `dns_lookup`, `check_server_health`, `scan_local_network`, `get_game_rules`) permettant a l'IA d'analyser le serveur et le reseau local, activables ou desactivables depuis les options IA de l'Administration.

### Corrections de bugs

- **Integrite du scoring de tournoi** : Correction d'erreurs `TypeError: '>' not supported between instances of 'NoneType' and 'int'` lors de la fermeture des tournois ou de l'avancement des manches de tournois FFA ayant des scores non saisis ou effaces (`None`).
- **Fiabilite des suites de tests unitaires** : Correction du script de test pour gerer les scores `None` au lieu de `0` lors de la simulation de scoring, rendant la suite de tests backend 100% passante.

---

## [1.7.0] - 2026-05-18

### Nouvelles fonctionnalites

- **Systeme de Versioning Automatise (AXE-30)** : Centralisation du suivi des versions sur un seul fichier `VERSION` racine et suppression des fichiers redondants pour eviter les desynchronisations.
- **Hook Git Pre-Push** : Automatisation d'un rappel push pour forcer la publication des releases et des tags correspondants sur GitHub.
- **Badge de Version en Direct** : Integration du badge dans la barre laterale du dashboard se mettant a jour via l'endpoint `/health`.

---

## [1.6.0] - 2026-05-16

### Nouvelles fonctionnalites

- **Configuration des Points de Tournoi (AXE-14)** -- Nouvelle interface d'administration pour definir les points par defaut :
  - Parametrage persistant (via `SystemConfig`) des gains pour Placement (1er, 2e, 3e), Participation (par match joue) et Bonus (par score).
  - Les formulaires de creation de tournois utilisent automatiquement ces valeurs par defaut.
- **Narrations IA Enrichies (G-25)** -- Le moteur de generation de messages de cloture est plus intelligent :
  - Remplacement des abbreviations techniques (R1, WB, LB) par des termes naturels comprehensibles.
  - Injection detaillee du detail des points (Placement, Bonus, Participation) dans le prompt pour des messages felicitant la regularite ou la performance.
  - Fix de la limite de contexte IA : le parametre `context_window` de l'administration s'applique dorenavant dynamiquement a la generation (num_predict) pour eviter que les longs messages ne soient tronques en JSON invalide.

### Corrections de bugs

- **Badge de Notifications Global** -- Fix du bug ou le compteur "1" de notification restait bloque dans le menu lateral apres avoir clique sur "Reessayer" ou supprime un message. Le statut se synchronise desormais instantanement sans necessiter un rechargement de page.
- **Securite JSON Ollama** -- Application du mode strict `format: "json"` sur les appels API de notifications pour empecher toute tentative de generation en Markdown par le modele.

---

## [1.5.0] - 2026-05-15

### Nouvelles fonctionnalites

- **Messagerie de Groupe & Inter-Equipes (AXE-12)** -- Deux nouveaux types de canaux de chat :
  - Chat d'equipe prive : clic sur le nom de sa propre equipe, salon reserve aux membres.
  - Chat inter-equipes : clic sur une equipe adverse, salon commun entre les deux equipes (trash-talk, coordination).
  - Channel keys deterministes (`team:NomEquipe`, `inter:EquipeA|EquipeB`) pour unicite garantie.
  - Sender names affiches dans les bulles de groupe.
  - Badge non-lu violet pulsant directement sur le nom de chaque equipe dans l'annuaire.
- **Gestionnaire de fichiers (AXE-13)** -- Section Fichiers utiles sur la page Informations :
  - Upload de fichiers par les admins (max 100 MB, noms sanitises, deduplication automatique).
  - Telechargement direct par les joueurs avec icones par type de fichier (.torrent, .zip, .pdf, .exe).
  - Suppression individuelle avec confirmation inline + bouton Nuke pour tout supprimer d'un coup.

### Ameliorations

- **Badge sidebar combine** -- Le compteur de messages non lus dans la sidebar cumule desormais les messages P2P + les messages de groupe via un store derive (`totalMsgUnread`).
- **WebSocket `group_message_new`** -- Nouveau type d'evenement temps reel pour les canaux de groupe, avec refresh automatique du chat ouvert et des badges.
- **Elements logistiques Plan de Salle (AXE-09)** -- Ajout d'elements de mobilier (Porte, Cuisine, Bar, WC, Rack technique, Ecran) dans l'editeur du plan de salle avec drag & drop et rotation.
- **Verrouillage de scores (AXE-15)** -- Delai de saisie 5s pour joueurs, verrouillage des matchs termines, indicateur visuel.
- **Proxy `/data`** -- Le frontend proxifie desormais `/data` vers le backend pour le telechargement de fichiers depuis le volume persistant.

---

## [1.4.0] - 2026-05-15

### Nouvelles fonctionnalites

- **Delai de saisie des scores (5s)** -- Les joueurs disposent d'un compte a rebours de 5 secondes avant la soumission effective du score.

### Securite & Integrite (AXE-15)

- **Verrouillage des scores finalises** -- Un joueur ne peut plus modifier un score de match termine. Seul un admin peut corriger un score valide.
- **Garde backend HTTP 403** -- L'endpoint `PUT /tournaments/{id}/score` rejette toute tentative de modification d'un match finalise par un non-admin.
- **Indicateur visuel** -- Les matchs verrouilles affichent un cadenas a la place du champ de saisie pour les joueurs concernes.

### IA & Outils

- **Tool `get_player_seat`** -- Nouveau tool IA pour localiser un joueur dans la salle (format T{table}_S{siege}) avec affichage des voisins de table.
- **Fuseau horaire corrige** -- Le tool `get_current_datetime` utilise desormais `Europe/Paris` pour l'heure locale LAN.
- **Fiabilite tool-calling** -- Refactoring du moteur `ia_queue.py` : detection d'outils sur un contexte minimal pour eviter les hallucinations du modele.

---

## [1.3.0] - 2026-05-15

- Page Joueurs avec badges messages non lus en temps reel
- Navigation chat directe depuis la liste joueurs
- Notifications synchronisees via store reactif partage
- Documentation README enrichie

## [1.2.0] - 2026-05-14

- Page d'informations generale (AXE-02) avec editeur Markdown admin
- Optimisation GPU (G-49) : animations CSS compositables
- Theme dynamique light/dark unifie
- Resolution noms d'equipes bracket triple couche (G-51)
- Auto-titre conversation IA inline SSE (G-50)

## [1.1.0] - 2026-05-13

- Systeme de notifications IA post-tournoi
- Widget statut IA temps reel
- Boutons Nuke admin pour purge bulk
- Blocage IA par joueur (ia_blocked)
- Spectateur bracket synchronise avec auto-cycling

## [1.0.0] - 2026-05-12

- Release initiale Alanbix
- Gestion tournois (Single/Double Elim, Round Robin, FFA)
- Plan de salle interactif
- Chat IA avec Ollama (multi-instance)
- Leaderboard global avec points distribues
- Vue spectateur projecteur
