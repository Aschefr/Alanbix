# Changelog

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
