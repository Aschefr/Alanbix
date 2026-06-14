# 📖 Documentation Alanbix (Français)

Bienvenue dans la base de connaissances d'**Alanbix**, le système de gestion de LAN party auto-hébergé assisté par l'IA.

Cette documentation est organisée de manière modulaire pour vous guider pas à pas dans l'installation, la configuration et l'utilisation de l'ensemble des fonctionnalités du système.

---

## 🧭 Plan de la Documentation

### 🚀 Démarrage Rapide
* **[Guide de Démarrage Rapide](quickstart.md)** : Tout pour déployer le système en Docker, créer le premier compte administrateur et configurer les paramètres de base.

### 🎮 Fonctionnalités et Modules (Features)
* 🏆 **[Moteur de Tournois](features/tournaments.md)** :
  * Les formats (Single, Double, Round Robin, FFA).
  * Inscriptions de masse, équipes de tournoi, bypass automatiques (BYEs).
  * Saisie des scores, verrouillage automatique (🔒) et annulations/rollback de points.
* 📊 **[Classements et Distinctions (Leaderboards & Awards)](features/leaderboards.md)** :
  * Leaderboard global individuel et mouvement (↑↓ NEW).
  * Leaderboard équipe globale (Modes pondéré vs brut).
  * Modale de statistiques du joueur et calcul des 12 distinctions de fin de LAN.
* 🗺️ **[Plan de Salle Interactif](features/room-plan.md)** :
  * Éditeur Drag & Drop (sièges, tables, éléments logistiques).
  * Sélection en libre-service par les joueurs et zoom centré sur le curseur.
  * Libération massive de sièges (Bulk Unassign).
* 🤖 **[Assistant IA (Ollama)](features/ai-assistant.md)** :
  * Réponses en streaming (SSE) et vectorisation de documents (RAG).
  * File d'attente prioritaire (`ia_queue`) et load balancing multi-instances.
  * Édition de messages, retry inline et compression automatique du contexte.
* 💬 **[Messagerie & Notifications](features/chat-notifications.md)** :
  * Conversations privées P2P rapides et channels d'équipes privés déterministes.
  * Centre de notifications unifié et commentaires de match générés par l'IA.
* 📋 **[Page d'Informations (Markdown)](features/info-page.md)** :
  * Éditeur WYSIWYG (EasyMDE), double vue (Joueur vs Projecteur) et détection des chemins de fichiers Windows (`\\serveur\partage`).
* 🛡️ **[Administration Système & Modération](features/administration.md)** :
  * Gestion complète des profils et mots de passe.
  * Bibliothèque de jeux et téléchargement automatique de jaquettes (SearXNG).
  * Monitoring des instances IA et boutons d'auto-destruction sécurisés (Purge/Nuke).
