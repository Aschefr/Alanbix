# 🌐 Gestion des Langues et Internationalisation (i18n)

Alanbix intègre un système complet de gestion des langues et des traductions directement depuis l'application. Il permet de traduire l'intégralité de l'interface utilisateur, de personnaliser les textes et d'ajouter de nouvelles langues pour les participants de la LAN.

---

## ⚙️ Architecture et Fonctionnement du Moteur i18n

### Le Système Double Couche (Merge)
Afin de concilier les mises à jour de l'application et les personnalisations locales faites par les organisateurs :
* **Dossier Usine (`static/i18n/`)** : Contient les traductions de référence livrées avec l'application (`fr.json`, `en.json`, etc.). Ces fichiers ne doivent pas être édités manuellement.
* **Dossier Utilisateur (`data/i18n/`)** : Dossier de persistance locale monté sur le serveur. Au premier démarrage, les fichiers usine y sont automatiquement copiés (seeding) s'ils n'existent pas.
* **Mécanisme de Fusion (Merge)** : Lors d'un appel API, le backend FastAPI charge d'abord le fichier de référence (usine) puis lui superpose (merge) les modifications apportées par l'utilisateur présentes dans le dossier utilisateur. Toute édition effectuée depuis l'application est écrite dans `data/i18n/`, garantissant ainsi la persistance lors de mises à jour de l'image Docker.

### Rendu Réactif Frontend
* **Store Svelte (`i18nStore.ts`)** : Le store gère le chargement asynchrone des traductions depuis l'API de fusion (`/api/i18n/{lang}`).
* **Helper réactif `$t(...)`** : Permet la traduction à la volée des textes avec support de l'interpolation de variables dynamiques (ex : `{$t('tournaments.started_by', { name: userName })}`).
* **Sélecteur de Langue** : Un menu déroulant équipé de drapeaux emojis est intégré à la barre latérale du dashboard. Le choix de l'utilisateur est stocké dans le `localStorage` pour persister entre les sessions.

---

## 🖥️ L'Interface d'Administration des Langues

Accessible via l'onglet **Administration > Traduction** (ou la route `/dashboard/admin/languages`).

### 1. Éditeur Bicolonne
L'interface propose une vue comparative côte-à-côté :
* **Colonne de gauche** : La langue de référence (le Français par défaut) dont les clés sont verrouillées.
* **Colonne de droite** : Les champs de saisie de la langue cible en cours d'édition. Les modifications sont sauvegardées de manière persistante au clic sur **Sauvegarder** ou par confirmation toast.

### 2. Navigation par Catégories
Les clés de traduction sont automatiquement catégorisées d'après leur préfixe (ex : `sidebar.*` dans "Sidebar", `ia.*` dans "Assistant IA", `tournaments.*` dans "Tournois"). 
* Une barre latérale permet de naviguer rapidement entre ces sections.
* Des badges affichent le nombre de clés manquantes ou vides pour chaque catégorie.
* L'état replié/déplié des catégories est conservé localement.

### 3. Recherche et Filtrage Temps Réel
Une barre de recherche permet de filtrer instantanément les clés par :
* Nom de la clé technique.
* Texte source (langue de référence).
* Texte cible (langue traduite).

---

## 🤖 Traduction Assistée par IA (Ollama)

Alanbix tire parti de l'instance d'IA locale Ollama configurée sur le serveur pour accélérer le processus de traduction :

* **Traduction Individuelle** : Un bouton d'action IA (icône ✨) situé à côté de chaque champ de saisie permet de traduire automatiquement le texte source vers la langue cible grâce au LLM.
* **Traduction en Masse (Bulk Translate)** : L'administrateur peut lancer une traduction automatique de tout le fichier ou uniquement des clés non-traduites. Le traitement est géré de manière asynchrone par la file d'attente IA (`ia_queue`), affichant une barre de progression en temps réel et un bouton d'annulation.
* **Formatage Strict** : Le prompt système force le modèle à retourner uniquement le texte traduit, en conservant les variables d'interpolation intactes (ex: `{count}`) et en évitant les guillemets ou introductions superflues.

---

## 🔄 Détection et Synchronisation des Clés Manquantes

Lorsqu'une nouvelle version d'Alanbix est déployée, de nouvelles clés de traduction peuvent faire leur apparition dans la langue de référence (`fr.json`).

* **Détection Automatique** : Le système compare la structure des clés du fichier de référence avec le fichier cible et calcule le nombre de clés manquantes structurellement (indiqué par une icône de clé rouge 🔑).
* **Bandeau d'Alerte** : Un bandeau d'avertissement s'affiche en haut de l'interface des langues si une désynchronisation structurelle est détectée.
* **Bouton Synchroniser** : Permet d'injecter en un clic toutes les clés manquantes dans le fichier cible avec une valeur vide, prêtes à être traduites manuellement ou via l'IA.
