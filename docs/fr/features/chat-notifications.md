# 💬 Messagerie Directe & Notifications

Alanbix intègre des canaux de communication en temps réel et un centre de notifications unifié permettant de fluidifier l'échange d'informations et d'animer l'événement.

---

## ✉️ Les Systèmes de Chat (Temps Réel)

Alanbix gère les flux de discussion via des connexions WebSocket persistantes (`/ws` géré dans `websockets.py`). Les messages sont instantanément transmis aux destinataires sans que ces derniers n'aient besoin de rafraîchir leur page.

### 1. Chat Privé de Joueur à Joueur (P2P)
* En cliquant sur un profil de joueur depuis l'annuaire, un espace de messagerie directe s'ouvre.
* Les messages sont stockés dans la table SQLite `messages`.
* Le système génère automatiquement des badges de notification rouges avec un compteur de messages non-lus sur le nom de l'expéditeur dans l'annuaire et sur l'onglet messagerie global de la barre latérale.

![Annuaire et Chat](../../screenshots/alanbix_joueurs.png)

### 2. Canaux de Groupe d'Équipe Déterministes (G-53)
Pour les besoins tactiques et communautaires de la LAN, Alanbix intègre un système de salons de groupe dont les clés d'identification sont calculées de manière déterministe côté serveur :
* **Chat d'équipe privé (🛡️)** : Réservé uniquement aux joueurs partageant le même `User.team_name`.
  * *Clé de canal* : `team:[NomDeLEquipe]` (ex: `team:Alpha Wolves`).
  * Les boutons d'accès de l'interface possèdent une animation de pulsation violette distinctive.
* **Chat inter-équipes (⚔️)** : Permet à deux équipes distinctes de s'envoyer des défis ou de discuter.
  * *Clé de canal* : `inter:[NomEquipeA]|[NomEquipeB]`. Les noms sont systématiquement triés par ordre alphabétique pour garantir que le canal soit identique quel que soit l'initiateur du chat.
  * *Contrôle de Sécurité* : Seuls les membres des deux équipes concernées (ou un administrateur) peuvent lire ou poster dans ce canal. Le backend réjete toute autre tentative.

---

## 🔔 Le Centre de Notifications (Temps Réel)

L'icône en forme de Cloche dans la barre latérale permet d'ouvrir le centre de notifications (table SQL `notifications`).

![Centre de Notifications](../../screenshots/alanbix_notifications.png)

### Les Différents Types de Notifications
1. **Notifications Admin (`admin`)** : Envoyées lorsqu'un organisateur publie une annonce générale ou répond manuellement à une conversation technique.
2. **Notifications de Tournoi IA (`tournament_ia`)** : Messages d'animation rédigés par l'assistant LLM local à la clôture d'un tournoi (voir ci-dessous).
3. **Notifications de Trophée (`award`)** : Alertes poussées en temps réel lorsqu'un joueur hérite ou se fait détrôner d'une distinction automatique (icône 🎁).

### Résumés de Matchs par l'IA
À la fermeture d'un tournoi, pour chaque participant, le serveur place une tâche de génération IA en file d'attente.
* **Le concept** : L'IA rédige une synthèse personnalisée, taquine ou encourageante de la performance du joueur durant le tournoi (ex: *"Tu as gagné tes 3 premiers matchs haut la main avant de trébucher en demi-finale face à PixelHunter... Ne lâche rien !"*).
* **Le Prompt Système de Notification** : Il est configurable par l'admin.
* **Résilience** : Si l'instance Ollama plante ou renvoie un timeout lors de la génération d'un message, le système de notification affiche une alerte d'erreur sur le tableau de bord de l'administrateur avec un bouton **"Relancer la génération"** pour re-soumettre la tâche dans la file d'attente IA sans bloquer le reste de l'application.
