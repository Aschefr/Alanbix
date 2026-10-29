# 📱 Application Mobile Compagnon & Paramètres (Android & iOS)

L'application mobile **Alanbix Compagnon** permet aux participants et organisateurs d'une LAN party de suivre leurs tournois, interagir avec la communauté et recevoir leurs alertes directement depuis leur smartphone, sans dépendre exclusivement de leur PC de jeu.

---

## 1. Ergonomie Mobile « Player-First »

Sur les écrans de smartphone ou tablettes (`<= 900px`), l'interface s'adapte automatiquement :
- **Masquage de la colonne latérale PC** et des fonctions d'administration ou de projection pour préserver l'espace utile.
- **Barre supérieure compacte** :
  - Logo et nom de l'événement LAN.
  - Raccourcis vers les infos de la LAN (📋), le plan de salle (📍), le centre de notifications (🔔) et l'écran des paramètres (⚙️).
- **Barre de navigation basse fixe** avec 5 onglets tactiles :
  1. `🏠 Accueil` : Onglets rapides **« ⚔️ Mes Matchs »** (cartes d'action prêtes à jouer, adversaire assigné, lien vers le poste et saisie de score) et **« 🌐 Chat Général »**.
  2. `🏆 Tournois` : Consultation des tournois en cours ou ouverts avec navigation tactile dans les arbres de tournoi.
  3. `💬 Messages` : Messagerie Joueur-à-Joueur et canal d'équipe en affichage *Master / Detail* (liste des joueurs puis discussion plein écran avec bouton retour).
  4. `🤖 Assistant` : Support technique IA avec tiroir latéral d'historique et appel aux administrateurs.
  5. `👤 Profil` : Statistiques de jeu, liste des distinctions et trophées remportés, et historique des points.

---

## 2. Triple Mode de Connexion & Découverte Réseau

L'application peut être configurée via la modale de connexion au serveur (accessible depuis les Paramètres ou au premier lancement) :
1. **Recherche automatique Wi-Fi (Auto-Discovery)** :
   - Détection des serveurs Alanbix sur le sous-réseau local (via broadcast mDNS et sonde IP/port 41481).
   - Connexion en 1 clic au serveur détecté.
2. **Saisie manuelle d'adresse IP ou de nom de domaine** :
   - Pour les connexions via routeur spécifique, VPN ou reverse proxy (`http://192.168.1.50:41481` ou `https://lan.domaine.org`).
3. **Mode Démo Hors-Ligne (Spécial Stores & Tests)** :
   - Permet d'explorer l'intégralité du tableau de bord avec des données simulées (matchs, messages, trophées) sans nécessiter de serveur physique en ligne.

---

## 3. Notifications Natives en LAN 100 % Locale

Contrairement aux applications classiques dépendantes des services cloud (Firebase FCM ou Apple APNs), Alanbix intègre un moteur autonome pour les réseaux locaux fermés :
- **Sur Android** :
  - Service au premier plan (`AlanbixPushService`) maintenant une connexion WebSocket OkHttp permanente vers le serveur LAN.
  - Fonctionne même écran verrouillé et après redémarrage de l'appareil (`RECEIVE_BOOT_COMPLETED`).
  - Prise en charge des canaux de notification Android (Matchs, Messages, Équipes, Annonces, Tournois).
  - Gestion des URL de lien profond (`alanbix://`) pour ouvrir instantanément la bonne conversation ou la saisie de score au toucher d'une notification.
- **Sur iOS** :
  - Support de l'extension *Local Push Connectivity* (`NEAppPushProvider`) activée sur le SSID Wi-Fi de la LAN.

---

## 4. Écran des Paramètres (`/dashboard/settings`)

L'écran des paramètres rassemble l'ensemble des réglages locaux de l'application :
- **État des notifications** : vérification des autorisations système, bouton d'alerte test, et gestion du service d'arrière-plan.
- **Filtrage par type d'alerte** : activation sélective (matchs à jouer, messages privés, chat d'équipe, mentions dans le chat général, réponses de l'IA, annonces admin, tournois).
- **Comportement & Discrétion** : vibrations, signaux sonores, et plage horaire du mode *Ne pas déranger* (avec options de dérogation pour les matchs prêts et les urgences admin).
- **Serveur LAN** : affichage de l'URL connectée, de la latence (ping ms), des SSIDs Wi-Fi déclarés et raccourci pour changer de serveur.
- **Apparence & Langue** : bascule de thème clair/sombre et sélection immédiate de la langue (`fr`, `en`, `es`).
- **Compte** : statut de session et déconnexion sécurisée (avec révocation du jeton d'appareil enregistré sur le serveur).

