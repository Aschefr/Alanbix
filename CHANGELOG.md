# Changelog

## [1.6.0] - 2026-05-16

### ✨ Nouvelles fonctionnalités

- **Configuration des Points de Tournoi (AXE-14)** — Nouvelle interface d'administration pour définir les points par défaut :
  - Paramétrage persistant (via `SystemConfig`) des gains pour Placement (1er, 2e, 3e), Participation (par match joué) et Bonus (par score).
  - Les formulaires de création de tournois utilisent automatiquement ces valeurs par défaut.
- **Narrations IA Enrichies (G-25)** — Le moteur de génération de messages de clôture est plus intelligent :
  - Remplacement des abréviations techniques (R1, WB, LB) par des termes naturels compréhensibles.
  - Injection détaillée du détail des points (Placement, Bonus, Participation) dans le prompt pour des messages félicitant la régularité ou la performance.
  - Fix de la limite de contexte IA : le paramètre `context_window` de l'administration s'applique dorénavant dynamiquement à la génération (num_predict) pour éviter que les longs messages ne soient tronqués en JSON invalide.

### 🐛 Corrections de bugs

- **Badge de Notifications Global** — Fix du bug où le compteur "1" de notification restait bloqué dans le menu latéral après avoir cliqué sur "Réessayer" ou supprimé un message. Le statut se synchronise désormais instantanément sans nécessiter un rechargement de page.
- **Sécurité JSON Ollama** — Application du mode strict `format: "json"` sur les appels API de notifications pour empêcher toute tentative de génération en Markdown par le modèle.

---

## [1.5.0] - 2026-05-15### ✨ Nouvelles fonctionnalités

- **Messagerie de Groupe & Inter-Équipes (AXE-12)** — Deux nouveaux types de canaux de chat :
  - 💬 **Chat d'équipe privé** : clic sur le nom de sa propre équipe → salon réservé aux membres (icône 🛡️).
  - ⚔️ **Chat inter-équipes** : clic sur une équipe adverse → salon commun entre les deux équipes (trash-talk, coordination).
  - Channel keys déterministes (`team:NomEquipe`, `inter:EquipeA|EquipeB`) pour unicité garantie.
  - Sender names affichés dans les bulles de groupe.
  - Badge « non-lu » violet pulsant directement sur le nom de chaque équipe dans l'annuaire.
- **Gestionnaire de fichiers (AXE-13)** — Section « 📦 Fichiers utiles » sur la page Informations :
  - Upload de fichiers par les admins (max 100 MB, noms sanitisés, déduplication automatique).
  - Téléchargement direct par les joueurs avec icônes par type de fichier (.torrent, .zip, .pdf, .exe…).
  - Suppression individuelle avec confirmation inline + bouton ☢️ Nuke pour tout supprimer d'un coup.
  
### 🔧 Améliorations

- **Badge sidebar combiné** — Le compteur de messages non lus dans la sidebar cumule désormais les messages P2P + les messages de groupe via un store dérivé (`totalMsgUnread`).
- **WebSocket `group_message_new`** — Nouveau type d'événement temps réel pour les canaux de groupe, avec refresh automatique du chat ouvert et des badges.
- **Badges non-lus réactifs** — Les badges 🛡️ (équipe, vert) et ⚔️ (inter, orange) se mettent à jour en temps réel via un objet Svelte `$: teamUnreads` dérivé réactif.
- **Bouton chat groupe élargi** — Le bouton `🛡️ Chat équipe` / `⚔️ Chat inter` est plus grand avec texte lisible, et pulse en violet (`btn-glow`) quand des messages sont non-lus.
- **Éléments logistiques Plan de Salle (AXE-09)** — Ajout d'éléments de mobilier (Porte, Cuisine, Bar, WC, Rack technique, Écran) dans l'éditeur du plan de salle avec drag & drop et rotation.
- **Verrouillage de scores (AXE-15)** — Délai de saisie 5s pour joueurs, verrouillage des matchs terminés, indicateur 🔒 visuel.
- **Proxy `/data`** — Le frontend proxifie désormais `/data` vers le backend pour le téléchargement de fichiers depuis le volume persistant.

### 📝 Documentation

- Ajout de la règle G-53 (Canaux de groupe déterministes) dans le cahier des charges.

---

## [1.4.0] - 2026-05-15

### ✨ Nouvelles fonctionnalités

- **Délai de saisie des scores (5s)** — Les joueurs disposent d'un compte à rebours de 5 secondes avant la soumission effective du score. Une barre de progression bleue animée s'affiche sous le match avec un bouton « ✕ Annuler » pour corriger avant envoi. Les admins contournent ce délai (soumission immédiate).

### 🔒 Sécurité & Intégrité (AXE-15)

- **Verrouillage des scores finalisés** — Un joueur ne peut plus modifier un score de match terminé (duel : les deux scores > 0 et différents / FFA : tous les placements renseignés). Seul un admin peut corriger un score validé.
- **Garde backend HTTP 403** — L'endpoint `PUT /tournaments/{id}/score` rejette toute tentative de modification d'un match finalisé par un non-admin.
- **Indicateur visuel 🔒** — Les matchs verrouillés affichent un cadenas à la place du champ de saisie pour les joueurs concernés.
- Couverture complète : Single Elim, Double Elim (WB+LB), Round Robin, FFA.

### 🤖 IA & Outils

- **Tool `get_player_seat`** — Nouveau tool IA pour localiser un joueur dans la salle (format T{table}_S{siège}) avec affichage des voisins de table.
- **Fuseau horaire corrigé** — Le tool `get_current_datetime` utilise désormais `Europe/Paris` pour l'heure locale LAN.
- **Fiabilité tool-calling** — Refactoring du moteur `ia_queue.py` : détection d'outils sur un contexte minimal (system + tools + dernier message) pour éviter les hallucinations du modèle.
- **Overhead tokens** — Constante `SYSTEM_OVERHEAD_TOKENS = 1300` intégrée au calcul de contexte frontend/backend.

---

## [1.3.0] - 2026-05-15

- Page Joueurs avec badges messages non lus en temps réel
- Navigation chat directe depuis la liste joueurs
- Notifications synchronisées via store réactif partagé
- Documentation README enrichie

## [1.2.0] - 2026-05-14

- Page d'informations générale (AXE-02) avec éditeur Markdown admin
- Optimisation GPU (G-49) : animations CSS compositables
- Thème dynamique light/dark unifié
- Résolution noms d'équipes bracket triple couche (G-51)
- Auto-titre conversation IA inline SSE (G-50)

## [1.1.0] - 2026-05-13

- Système de notifications IA post-tournoi
- Widget statut IA temps réel
- Boutons Nuke admin pour purge bulk
- Blocage IA par joueur (ia_blocked)
- Spectateur bracket synchronisé avec auto-cycling

## [1.0.0] - 2026-05-12

- Release initiale Alanbix
- Gestion tournois (Single/Double Elim, Round Robin, FFA)
- Plan de salle interactif
- Chat IA avec Ollama (multi-instance)
- Leaderboard global avec points distribués
- Vue spectateur projecteur
