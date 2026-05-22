# Changelog

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
