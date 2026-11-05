# 🛡️ Administration Système & Contrôles

Le panneau d'administration d'Alanbix (accessible uniquement aux utilisateurs ayant `is_admin = true` en base de données) regroupe les outils de modération, la gestion des jeux, et les commandes de maintenance de l'application.

---

## 🧭 Configuration guidée du serveur

Le premier compte créé sur un serveur neuf (l'administrateur) arrive sur **Configuration du serveur** (`/dashboard/setup`) au lieu de l'accueil joueur. Neuf étapes, chacune pouvant être passée :

1. **L'événement** : nom de la LAN et langue par défaut.
2. **Le réseau** : noms du Wi-Fi de la LAN (reconnus par l'application mobile) et adresse à donner aux joueurs (avertissement si c'est une adresse `localhost`).
3. **La page Infos** : modèle prérempli (horaires, Wi-Fi, repas, règles générales) à compléter dans l'éditeur Markdown.
4. **Jeux et tournois** : vérification de SearXNG (avec l'aide pour l'installer), ajout de jeux avec leur jaquette, les quatre formats expliqués avec un exemple de règles, le barème de points expliqué, et un premier tournoi créé sur place.
5. **L'assistant Alanbix** (facultatif) : pas d'assistant, un modèle local (Ollama) ou un service en ligne avec une clé d'API ; test de connexion, choix du modèle et taille de contexte.
6. **La base de connaissances** (facultatif) : à quoi servent les fiches et comment bien les écrire, installation du modèle de recherche intégré (135 Mo), et quelques questions que la page Infos ne couvre pas (contact, matériel à emprunter, parking, couchage) : chaque réponse devient une fiche.
7. **Le plan de salle** (facultatif) : générateur de tables (nombre de tables, places par table, tables par rangée) avec aperçu.
8. **Inviter les joueurs** : adresse, QR code et affiche imprimable.
9. **Récapitulatif** : « Terminer » ou « Je participe aussi » (enchaîne sur l'accueil joueur).

La progression est enregistrée sur le serveur (`admin_setup`). L'administration affiche un bandeau tant que la configuration n'est ni terminée ni masquée, et **Réglages › Général › Configuration guidée** la relance. Après une réinitialisation complète, elle réapparaît.

![Configuration guidée](../../../screenshots/fr/setup.png)

---

## 🎚️ Régie (onglet par défaut)

La Régie rassemble ce qui demande l'attention de l'organisateur pendant la LAN :
* **Appels à l'aide** : demandes d'escalade venues de l'assistant IA. « Voir » ouvre la conversation d'origine (ou la plus récente du joueur) ; à défaut, « Écrire au joueur » ouvre ses messages privés. « Résolu » et « Ignorer » clôturent la demande.
* **Matchs à saisir** : scores du tour en cours, saisissables directement ; « Voir » ouvre le tournoi concerné.
* **Modération rapide** : recherche d'un joueur puis bouton « ⋯ » : couper le chat (15 min, 30 min, 1 h, 24 h) ou le rétablir, bloquer l'IA, écrire au joueur, ou ouvrir sa fiche complète dans Gestion Joueurs.
* **Tournois en cours** : progression de chaque tournoi.

![Régie](../../../screenshots/fr/admin_regie.png)

Les autres onglets : **Tournois & Jeux**, **Joueurs**, **Réglages**, **Conversations IA**, **Prix & Distinctions**, **Diagnostic** et **Langues**.

---

## 👥 Gestion des Comptes Joueurs

Accessible via l'onglet **Administration › Joueurs**.

### Actions Individuelles
* **Création manuelle** : L'administrateur peut enregistrer un joueur directement via le formulaire en définissant son pseudo, mot de passe initial, et équipe.
* **Édition & Réinitialisation** : Possibilité de modifier le pseudo, de réinitialiser le mot de passe d'un participant (en cas d'oubli), d'éditer son nom d'équipe globale, ou de lui attribuer les privilèges d'administrateur.
* **Modération IA** : L'administrateur peut révoquer l'accès à l'assistant IA pour un joueur s'il en abuse (ce qui masque le chat IA de son interface).

![Gestion des Joueurs](../../../screenshots/fr/admin_players.png)

### Génération d'un Pool de Test (G-46)
Pour valider le bon fonctionnement des brackets de tournoi ou de la messagerie sans avoir à créer manuellement 20 comptes :
* **Le Bouton** : Cliquez sur le bouton **"Générer 20 joueurs de test"** (`POST /admin/users/generate-test-pool`).
* **Résultat** : Crée instantanément 20 comptes de joueurs fictifs (mot de passe `test`, points à zéro) avec des pseudonymes de type gamers (ex: `FragMaster2000`, `CyberWolf`, etc.), répartis équitablement dans 4 équipes prédéfinies (*Alpha Wolves*, *Neon Vipers*, *Shadow Foxes*, *Iron Bears*). Cette opération est idempotente : elle n'écrase pas les pseudos déjà existants. À réserver aux essais, puisque tout le monde connaît ce mot de passe.

---

## 🎮 Bibliothèque de Jeux (SearXNG Proxy)

Pour associer une image et un règlement aux tournois, les administrateurs gèrent un catalogue local de jeux.
* **Création d'un Jeu** : Allez dans **Administration › Tournois & Jeux**, section **Bibliothèque**, puis **Ajouter un Jeu**.
* **Recherche de jaquette automatique** : Pour éviter d'avoir à télécharger et héberger vous-même l'image d'un jeu, saisissez le nom du jeu et cliquez sur le bouton Loupe de recherche. Le serveur interroge en arrière-plan un moteur SearXNG (proxy local) pour récupérer l'image officielle et l'enregistrer localement dans `/app/data/game_images/` (volume persistant) afin de garantir l'offline-first de la LAN.
* **Upload manuel** : L'administration permet également de téléverser une image de couverture directement depuis le disque dur du PC de l'administrateur, qui sera stockée de manière persistante.

![Gestion de la Bibliothèque de Jeux](../../../screenshots/fr/admin_games.png)

---

## 🎛️ Réglages

L'onglet **Réglages** a deux parties : **Général** (Événement, Tournois, Chat & modération, Services, Zone dangereuse) et **Intelligence Artificielle** (Serveurs, Modèle, Comportement, Consignes, Connaissances). Les modifications y sont enregistrées automatiquement, et chaque option est expliquée sur place.

* **Renommage de la LAN** : Le changement est sauvegardé via `PUT /admin/config/event_name` et se met à jour en temps réel sur les dashboards de tous les participants grâce au WebSocket.

![Paramètres d'Administration](../../../screenshots/fr/admin_settings.png)


---

## ☢️ Contrôles d'Auto-Destruction (Boutons NUKE) (G-08)

Pour faciliter le nettoyage de la base de données entre deux événements ou après des phases de tests intensifs, la **Zone dangereuse** (**Réglages › Général**) propose des boutons de purge massive (dits **Boutons NUKE**) :

* **Purger le chat public** : supprime définitivement tous les messages du chat public et leurs images, et retire le message épinglé.
* **Tournois** : supprime tous les tournois, arbres, scores, équipes de tournoi et remet les points de tous les joueurs à zéro.
* **Joueurs** : supprime tous les comptes non administrateurs avec leurs messages, conversations IA, notifications, appareils et images envoyées ; leur pseudo est retiré des classements des tournois terminés.
* **Jeux** : supprime tous les jeux (et donc les tournois), leurs jaquettes téléversées et miniatures, et les fiches de la base de connaissances propres à un jeu.
* **Images** : supprime toutes les images envoyées (assistant IA, messages privés et d'équipe, chat public) et retire leurs références dans les messages.
* **Notifications** : supprime les notifications de tous les joueurs.
* **Distinctions** : supprime les distinctions attribuées et les textes personnalisés, puis recalcule les distinctions par défaut.
* **Plan de salle** : supprime toutes les tables, places et éléments du plan, et libère la place de chaque joueur.
* **Réinitialisation complète** : vide tout le serveur comme une nouvelle installation (toutes les données, tous les fichiers téléversés, les réglages et les traductions personnalisées). Les comptes administrateurs peuvent être conservés (pseudo, mot de passe, avatar). Il faut taper `RESET` pour confirmer ; les autres personnes connectées sont rechargées automatiquement.

![Zone dangereuse](../../../screenshots/fr/admin_danger_zone.png)

### Ergonomie de Sécurité (Pas de window.confirm)
Aucune purge n'utilise la boîte de dialogue du navigateur (`window.confirm`) : la confirmation s'affiche dans l'interface, et un second clic est nécessaire. La réinitialisation complète demande en plus de taper `RESET`.

---

## 📚 Base de Connaissances IA (RAG)

Pour alimenter la mémoire de l'assistant IA local (RAG) :
* **Où** : **Administration › Réglages › Intelligence Artificielle › Connaissances**. Chaque fiche est enregistrée dans la table `knowledge_base`.
* **Ajouter une fiche** : le texte est indexé aussitôt pour la recherche par mots-clés, et pour la recherche par le sens si un modèle d'embedding répond. Voir [l'assistant IA](ai-assistant.md).
* **Gérer les fiches** : modification et suppression fiche par fiche, bandeau d'état de la recherche et bouton **Réindexer les fiches**.
* **Suggestions** : quand l'assistant ne trouve pas une réponse, il peut proposer une fiche, que l'administrateur approuve ou refuse dans l'onglet **Conversations IA**.

![Base de connaissances](../../../screenshots/fr/admin_knowledge.png)

---

## 📡 Onglet Diagnostic

État du serveur (processeur, mémoire, disque) et tests réseau lancés à la main : ping, traceroute et DNS, avec le résultat en clair. Les tests partent du serveur Alanbix, pas de l'ordinateur de l'administrateur ni de celui d'un joueur.

![Diagnostic](../../../screenshots/fr/admin_diagnostics.png)

## 🩺 Diagnostic mémoire du serveur
Pour surveiller un serveur qui tourne depuis longtemps (par exemple un Raspberry Pi), l'API expose `GET /admin/diagnostics/memory`, réservé aux administrateurs (même session que l'application, même port).

- **Réponse par défaut** : mémoire du processus (`rss_mb`), nombre de connexions WebSocket, joueurs en ligne, file d'attente IA, caches et tâches asynchrones. Si l'un de ces compteurs grimpe sans jamais redescendre, c'est le signe d'une fuite.
- **`?top=30`** : liste les types d'objets Python les plus nombreux ; comparez deux appels espacés pour voir ce qui s'accumule.
- **`?trace=start`** puis **`?trace=diff`** : enregistre les allocations, puis affiche les lignes de code qui retiennent le plus de mémoire. **`?trace=stop`** arrête l'enregistrement (il ralentit le serveur : à n'utiliser que pour une analyse).

> Les connexions WebSocket n'utilisent plus la compression par message : chaque connexion en gardait un contexte de ~37 Ko, jamais libéré quand le réseau coupait brutalement (téléphone en veille). Voir le changelog 1.35.2.
