# 📊 Classements, Statistiques & Distinctions (Awards)

Alanbix propose un système complet pour suivre les performances individuelles et collectives tout au long de la LAN. Les classements sont calculés à la fois de manière persistante (en base de données) et de manière prévisionnelle (temps réel frontend).

---

## 🏆 Le Leaderboard Global Individuel

Accessible depuis l'onglet principal du Dashboard. Il liste les joueurs triés par ordre décroissant de leurs points accumulés dans la table `users`.

### Les Indicateurs de Progression (↑↓ NEW)
Pour rendre le classement dynamique, le frontend mémorise le dernier état du leaderboard dans la variable `previousLeaderboard` (persistance temporaire en mémoire locale).
À chaque rafraîchissement des données (via API ou WebSocket) :
* Si un joueur monte de $N$ places : Un badge vert **↑N** apparaît à côté de son nom.
* Si un joueur descend de $N$ places : Un badge rouge **↓N** apparaît.
* Si un joueur n'était pas présent dans le Top 10 lors du snapshot précédent et y fait son entrée : Un badge orange **NEW** s'affiche.
* Si sa position est inchangée : Aucun badge n'est affiché.

---

## 👥 Le Leaderboard des Équipes

Ce classement groupe les joueurs par la valeur de leur colonne `User.team_name` (leur équipe globale déclarée sur leur profil). Les lignes d'équipes sont colorées en violet (`var(--primary-purple)`) pour se distinguer du classement individuel.

### Les 2 Modes de Calcul de Score
L'administrateur peut choisir le mode de calcul depuis l'onglet **Administration > Paramètres** (clé de configuration SQLite `team_scoring_mode`) :

1. **Mode Brut (`raw`)** :
   $$\text{Score Équipe} = \sum \text{Points de tous les membres}$$
   *Idéal si toutes les équipes ont le même nombre de joueurs.*
2. **Mode Pondéré (`weighted`)** :
   $$\text{Score Équipe} = \frac{\sum \text{Points de tous les membres}}{\text{Nombre de membres de l'équipe}}$$
   *Recommandé si la taille des équipes est déséquilibrée. Cela évite qu'une équipe de 8 joueurs écrase systématiquement une équipe de 3 joueurs.*

### Vue Expandable (Détail des membres)
Cliquer sur une ligne d'équipe dans le classement déploie instantanément un panneau listant tous les membres de cette équipe triés par points individuels, montrant ainsi la contribution exacte de chaque membre au score global.

---

## 🗂️ Fiche Joueur & Modale de Statistiques
Cliquer sur le nom d'un joueur n'importe où sur l'application (leaderboards, annuaire, arbre de tournoi) ouvre une modale de profil complète (fond opaque `var(--bg-secondary)`) qui affiche :
1. **Statistiques Clés** : Score total, nombre de tournois disputés, et trophées remportés.
2. **Historique des Matchs** : La liste complète des tournois auxquels le joueur a participé. Pour chaque tournoi, un badge couleur indique le statut (**INSCRIT**, **EN COURS**, **TERMINE**), sa place finale, et le détail du calcul des points obtenus (ex: +10 victoire, +1 participation, +1.5 buts).
3. **Vitrine de Trophées** : Les distinctions automatiques décernées au joueur.

![Profil Joueur](../../screenshots/alanbix_profile_joueur.png)

---

## 🎁 Le Système de Distinctions Automatiques (Awards)

À chaque clôture de tournoi, le serveur exécute un pipeline d'analyse statistique sur l'ensemble de la base de données SQLite pour attribuer ou réassigner automatiquement 12 trophées spécifiques (table `awards`).

### Les 12 Trophées Gérés
1. **Premier de la LAN** : Joueur occupant la 1ère place du classement général.
2. **Équipe première de la LAN** : Équipe occupant la 1ère place du classement équipes.
3. **Le Bourreau** : Joueur ayant infligé le plus grand nombre de défaites (rounds de brackets perdus) aux autres joueurs.
4. **Le Roi du Coop** : Joueur comptabilisant le plus de victoires dans des tournois joués en mode Équipe.
5. **Loup Solitaire** : Joueur comptabilisant le plus de victoires dans des tournois joués en mode Solo (1v1).
6. **Le Marathonien** : Joueur ayant disputé le plus grand nombre total de matchs, tous tournois confondus.
7. **Gâchette Facile** : Joueur ayant le score cumulé (buts/points marqués dans les matchs) le plus élevé.
8. **La Passoire** : Joueur ayant le score cumulé le plus bas parmi les matchs joués.
9. **Chouchou des BYE** : Joueur ayant bénéficié du plus grand nombre de BYE (trous dans le bracket l'ayant fait avancer sans jouer).
10. **Le Suisse** : Joueur ayant obtenu le plus grand nombre de matchs nuls (draws).
11. **Survivant du Losers Bracket** : Joueur ayant disputé le plus de matchs dans le Losers Bracket.
12. **L'Important c'est de participer** : Joueur ayant obtenu le moins de victoires parmi ceux ayant disputé au moins 2 matchs de tournoi.

### Notifications et Personnalisation
* **Notification Temps Réel** : Lorsqu'un trophée change de mains suite à la clôture d'un tournoi, le serveur pousse instantanément une notification WebSocket (icône 🎁) au joueur qui vient de remporter la distinction.
* **Personnalisation Admin** : Les titres et descriptions des distinctions peuvent être édités dans l'administration. Les descriptions supportent des variables dynamiques interpolées par le serveur lors de l'affichage (ex: `{points}`, `{wins}`, `{matches_played}`).

---

## 📊 Le Classement Prévisionnel (Live Standings)

Lorsqu'un tournoi est au statut **RUNNING** (en cours de jeu) :
* Le système calcule dynamiquement côté frontend un classement provisoire basé sur l'état actuel des matchs du bracket (nombre de victoires accumulées $\times$ points par victoire + scores marqués $\times$ multiplicateur de buts).
* Ce classement s'affiche sous forme de mini-leaderboard directement sous le bracket avec un badge clignotant **LIVE**.
* *Sécurité d'intégrité* : Ce calcul est purement visuel et n'altère en aucun cas la colonne `points` en base de données SQL tant que l'administrateur n'a pas validé la clôture officielle du tournoi.
