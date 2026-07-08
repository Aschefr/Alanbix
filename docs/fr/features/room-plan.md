# 🗺️ Plan de Salle Interactif

Le plan de salle interactif d'Alanbix permet de représenter graphiquement la disposition physique de la LAN, de gérer l'attribution des sièges et de faciliter la localisation des participants.

---

## 🛠️ L'Éditeur de Salle (Vue Administrateur)

Accessible depuis **Administration > Plan de salle**. Cet éditeur permet de concevoir le plan physique de l'événement grâce à un canevas 2D interactif.

### Les Éléments Disponibles (Palette Latérale)
Vous pouvez faire glisser par Drag & Drop (Glisser-Déposer) les éléments suivants sur le canevas :
* **Siège** : L'élément principal sur lequel un joueur peut s'asseoir.
* **Table** : Meubles de différentes dimensions pour structurer les rangées.
* **Éléments Structurels** : Murs, Portes, Racks Techniques, Écrans de projection.
* **Éléments de Vie** : Coin Cuisine, Bar de ravitaillement, Sanitaires (WC).

![Éditeur de Salle](../../../screenshots/alanbix_plan_salle_editeur.png)

### Actions sur les Éléments du Canevas
* **Sélection et Déplacement** : Cliquez sur un élément et maintenez enfoncé pour le repositionner.
* **Rotation coordonnée** : Cliquer sur la poignée de rotation d'une table et la faire pivoter déplace et oriente automatiquement tous les sièges associés en arc de cercle autour du centre de la table.
* **Confirmation de suppression (Table)** : Supprimer une table affiche une boîte de confirmation visuelle (`✓` / `✕`) positionnée en haut à droite au-dessus de la table pour éviter tout clic accidentel, et supprime automatiquement en cascade tous les sièges associés à cette table.
* **Ajout direct de siège** : Un bouton vert `+` (siège fantôme) s'affiche sur le prochain slot de grille physique libre d'une table. Cliquer dessus génère un siège avec un ID séquentiel unique (ex. `T5_S9` au lieu d'IDs conflictuels). Le bouton se déplace ou disparaît automatiquement en fonction du redimensionnement de la table et de sa capacité maximale.
* **Recentrage automatique serré** : Le bouton **Recentrer** (ainsi que le chargement initial du plan) calcule dynamiquement la boîte englobante de tous les éléments (tables, chaises, décorations) pour ajuster le zoom et centrer le plan de salle avec une marge optimisée de 15px.
* **Sauvegarde** : Les modifications se synchronisent automatiquement en arrière-plan avec la table SQLite `room_items`.

---

## 🪑 L'Assignation des Places

Le système gère l'association entre les comptes utilisateurs et les identifiants de sièges placés sur la carte.

### Choix en Libre-Service (Joueur)
* Depuis la vue Plan de Salle publique, un joueur connecté peut cliquer sur un siège libre pour le réserver.
* Son pseudo et son avatar apparaissent immédiatement sur le plan pour tous les autres utilisateurs grâce à la synchronisation WebSocket.
* Si le joueur change d'avis, il peut cliquer sur son propre siège pour "Libérer la place".

![Plan de Salle Zoom](../../../screenshots/alanbix_plan_salle_zoom.png)

### Administration et Assignation Manuelle
* L'administrateur peut cliquer sur n'importe quel siège et utiliser un menu déroulant contenant la liste des joueurs inscrits pour affecter manuellement un participant à un poste.
* **Bouton "Libérer tout" (Bulk Unassign)** : Situé dans l'en-tête de l'éditeur d'administration. Ce bouton envoie une requête `POST /room/admin-unassign-all` au backend pour désassigner instantanément tous les joueurs de la salle d'un seul coup (pratique lors de la réinitialisation de l'événement).

---

## 🖱️ Navigation Avancée : Zoom Centré sur le Curseur

Pour offrir une expérience fluide, le plan de salle dispose d'un moteur de manipulation 2D (Pan & Zoom) codé en Vanilla JS sans aucune dépendance externe lourde.

* **Zoom Centré** : L'utilisation de la molette de la souris oriente le facteur d'échelle directement vers la position physique du pointeur de la souris (et non vers le coin supérieur gauche du conteneur).
* **Pan (Déplacement)** : Maintenez le bouton gauche de la souris enfoncé (ou glissez avec un doigt sur tablette/mobile) pour faire glisser le plan.
* **Filtre de Sécurité Drag-Threshold** : Le système applique un seuil de pixels minimum avant de valider un déplacement. Cela évite de déplacer accidentellement la carte lorsqu'un joueur souhaite simplement cliquer sur son siège.

---

## 🔗 Synergie avec les Brackets de Tournois

Une fonctionnalité unique d'Alanbix est le croisement de données entre l'emplacement physique et l'état des matchs de tournoi :
* Dans l'arbre d'un tournoi actif, à côté du pseudo de chaque joueur dans un match, apparaît un petit badge représentant son numéro de siège (ex: **#B12**).
* **Clic de Localisation** : Cliquer sur ce badge de siège téléporte l'utilisateur directement sur la vue Plan de Salle, centre automatiquement la caméra sur le poste de ce joueur et applique une animation de pulsation pour le mettre en évidence.
