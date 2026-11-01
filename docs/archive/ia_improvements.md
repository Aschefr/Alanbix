> **Document historique — ne fait plus foi.** Liste d'idées pour l'assistant IA rédigée en juillet 2026 (v1.20–v1.21).
> L'assistant a été largement repris depuis (v1.35.1 : prompt en couches, guide de l'application, langue du joueur,
> base de connaissances avec seuil de pertinence). Voir `CHANGELOG.md` et `docs/fr/features/ai-assistant.md` pour l'état actuel.

# 🤖 Alanbix IA — Suggestions d'amélioration

> Nouvelles fonctionnalités suggérées pour enrichir l'assistant IA.  
> Données disponibles en base, complexité estimée par item.

---

## ✅ Livré en v1.20.0

- [x] **`get_live_matches`** — Matchs en cours sur tous les tournois actifs
- [x] **`get_team_roster`** — Composition complète d'une équipe
- [x] **`get_player_match_history`** — Historique des résultats d'un joueur
- [x] **`get_awards`** — Distinctions en cours de calcul (leaders par catégorie)
- [x] **`get_upcoming_matches`** — Prochains matchs non joués
- [x] **`get_files`** — Fichiers disponibles au téléchargement
- [x] **`get_player_rank_progression`** — Évolution du classement d'un joueur
- [x] **`get_bracket_detail`** — Arbre complet d'un bracket
- [x] **`get_leaderboard_by_game`** — Classement par jeu
- [x] **`get_tournament_bracket_path`** — Chemin parcouru par un joueur
- [x] **`send_notification_to_player`** — Envoyer une notification à un joueur
- [x] **`announce_to_all`** — Diffuser une annonce globale (admins uniquement)

## ✅ Livré en v1.21.0 — Améliorations UX du chat IA

- [x] **Horodatage des messages** — Heure d'envoi sur chaque bulle (utilisateur + IA)
- [x] **Auto-nommage v2** — Utilise jusqu'à 3 échanges (6 messages) pour un titre plus pertinent
- [x] **Renommage manuel** — Bouton ✏️ + modal avec suggestion IA via la file d'attente
- [x] **Suggestion IA fire-and-forget** — Tâche `title_suggestion` dans `IAQueueManager`, résultat via WebSocket
- [x] **Fix retry pipeline** — Propagation de `full_response` corrigée dans le SSE
- [x] **Fix ghost message** — Message parasite au redémarrage backend éliminé
- [x] **`api.patch()`** — Méthode manquante ajoutée au helper API frontend

---

## 🥇 Haute priorité — Prochaines étapes

- [ ] **`get_connected_players`** — Nombre de joueurs actifs sur la plateforme  
  *"Il y a 12 joueurs connectés" — ambiance, décompte*  
  → Données dispo : à implémenter (présence WebSocket ou last_seen)

- [ ] **`submit_score`** — Soumettre un score via l'IA (avec confirmation double)  
  *"Dis à l'IA que t'as gagné 3-1 et elle enregistre le résultat"*  
  → Complexité : élevée — nécessite validation + protection anti-triche

- [ ] **`create_poll`** — Lancer un vote rapide parmi les joueurs  
  *"Pause pizza dans 30min ? Vote oui/non" — engagement communautaire*  
  → Nécessite : nouveau modèle `Poll` + UI de vote côté joueur

---

## 🥈 Idées futures — Chat IA

- [ ] **Recherche dans les conversations** — Barre de recherche full-text dans la sidebar  
  → Backend : index SQLite FTS5 ou simple `LIKE` sur `ChatMessage.content`

- [ ] **Export de conversation** — PDF ou Markdown d'une conversation complète

- [ ] **Épingler des conversations** — Conversations favorites toujours en tête de liste

- [ ] **Réactions aux messages** — Emoji quick-reactions sur les réponses IA

---

## 📌 Priorité suggérée

**Prochain sprint** : `get_connected_players` (ambiance live) puis `create_poll` (engagement).  
`submit_score` en dernier — complexité et risque de triche à encadrer correctement.
