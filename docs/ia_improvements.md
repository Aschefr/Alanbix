# 🤖 Alanbix IA — Suggestions d'amélioration

> Nouvelles fonctionnalités suggérées pour enrichir l'assistant IA.  
> Données disponibles en base, complexité estimée par item.

---

## 🥇 Haute priorité — Lecture (fort impact, facile)

- [ ] **`get_live_matches`** — Tous les matchs en cours sur l'ensemble des tournois actifs  
  *L'IA peut commenter en direct, annoncer les affrontements, créer du drama. Ex : "T1 vs T4 en ce moment dans le tournoi CS !"*  
  → Données dispo : parcourir `bracket` des tournois `RUNNING`, filtrer les matchs sans scores

- [ ] **`get_team_roster`** — Composition complète d'une équipe (membres, points, tournois)  
  *Répondre aux questions "Qui est dans l'équipe des Fouines ?" très courantes*  
  → Données dispo : `TournamentTeam` + `TournamentTeamMember` + `User`

- [ ] **`get_player_match_history`** — Historique des résultats passés d'un joueur  
  *Permettre les anecdotes, streaks, "tu as perdu 3 fois de suite contre Machin"*  
  → Données dispo : brackets archivés des tournois `CLOSED` + `DONE`

- [ ] **`get_awards`** — Distinctions en cours de calcul (leaders par catégorie)  
  *"Qui est en train de gagner le titre 'Marathon' ?" — tension narrative*  
  → Données dispo : logique awards déjà présente dans le backend

---

## 🥈 Moyenne priorité — Lecture

- [ ] **`get_upcoming_matches`** — Prochains matchs non joués de toute la LAN  
  *Programme de la journée, "tu joues dans 20 min contre Bidule"*  
  → Données dispo : bracket RUNNING, filtrer les matchs sans scores et avec 2 joueurs connus

- [ ] **`get_files`** — Fichiers disponibles au téléchargement (torrents, patchs, configs)  
  *"Où je télécharge le serveur dédié de CS ?" — actuellement non accessible à l'IA*  
  → Données dispo : gestionnaire de fichiers admin déjà en place

- [ ] **`get_player_rank_progression`** — Évolution du classement d'un joueur (avant/après tournoi)  
  *"Tu étais 3ème hier soir, tu es tombé 5ème" — narrative coaching et pique amicale*  
  → Données dispo : points historiques dans les `results` des tournois `CLOSED`

- [ ] **`get_bracket_detail`** — Arbre complet d'un bracket (qui reste, qui est éliminé)  
  *Expliquer le parcours d'un joueur, visualiser les chemins vers la finale*  
  → Données dispo : `bracket` JSON du tournoi

---

## 🥉 Nice-to-have

- [ ] **`get_connected_players`** — Nombre de joueurs actifs sur la plateforme  
  *"Il y a 12 joueurs connectés" — ambiance, décompte*  
  → Données dispo : à implémenter (présence WebSocket ou last_seen)

- [ ] **`get_leaderboard_by_game`** — Classement des joueurs sur un jeu précis  
  *"Qui est le meilleur à Trackmania ici ?" — rivalités ciblées*  
  → Données dispo : croiser `TournamentParticipant` + `results` filtrés par `game_id`

- [ ] **`get_tournament_bracket_path`** — Chemin parcouru par un joueur dans le bracket  
  *Raconter l'histoire du tournoi d'un joueur match par match*  
  → Données dispo : bracket + entity_id du joueur

---

## ✍️ Outils d'écriture — Le vrai saut qualitatif

> Actuellement l'IA est **100% lecture**. Ces outils d'écriture transformeraient l'assistant en acteur de la LAN.

- [ ] **`send_notification_to_player`** — Envoyer une notification à un joueur spécifique  
  *"Va dire à Zork que son match commence dans 5 minutes"*  
  → Impact : ⭐⭐⭐⭐⭐ — utile pour les admins qui délèguent à l'IA

- [ ] **`announce_to_all`** — Diffuser une annonce globale (admins uniquement)  
  *Annoncer une pause, un changement de planning, une urgence via l'IA*  
  → Contrainte : restreindre aux admins dans le système prompt + vérification backend

- [ ] **`submit_score`** — Soumettre un score via l'IA (avec confirmation double)  
  *"Dis à l'IA que t'as gagné 3-1 et elle enregistre le résultat"*  
  → Complexité : élevée — nécessite validation + protection anti-triche

- [ ] **`create_poll`** — Lancer un vote rapide parmi les joueurs  
  *"Pause pizza dans 30min ? Vote oui/non" — engagement communautaire*  
  → Nécessite : nouveau modèle `Poll` + UI de vote côté joueur

---

## 📌 Recommandation

**Commencer par `get_live_matches`** — 30 lignes dans `ia_tools.py`, zéro nouveau modèle,  
et c'est ce qui transforme l'IA d'un assistant passif en **commentateur vivant de la LAN**.
