# Guide de Développement et Publication (Alanbix)

Ce document explique le workflow de développement local et la procédure pour publier une nouvelle version d'Alanbix pour les environnements de production (notamment Unraid).

## 🏗️ Architecture : Dev vs Prod

Alanbix utilise deux architectures différentes selon l'environnement, afin de tirer parti du meilleur des deux mondes :

### 1. Environnement de Développement (Local)
En développement, nous utilisons l'approche classique "2 conteneurs" via `docker-compose.yml` :
- **Backend (Python/FastAPI)** : Tourne sur le port `8000`.
- **Frontend (SvelteKit/Vite)** : Serveur Vite en mode dev (port `5173` dans le conteneur), exposé sur le port `41481` de la machine.
- **Pourquoi ?** Cela permet d'utiliser le *Hot Module Replacement* (HMR) de Vite pour le frontend. Le code se met à jour en temps réel à chaque sauvegarde de fichier.

### 2. Environnement de Production (Unraid / Docker Hub)
En production, le but est d'avoir le déploiement le plus simple possible pour l'utilisateur final. Nous utilisons donc un **conteneur unique** via `Dockerfile.standalone` :
- Le frontend SvelteKit est compilé en de simples fichiers statiques (HTML/JS/CSS) via l'adaptateur `adapter-static` (mode SPA).
- Le backend FastAPI se charge à la fois de faire tourner l'API, **et** de servir ces fichiers statiques sur un port unique (`41481`).
- **Pourquoi ?** Un seul conteneur à gérer pour les utilisateurs finaux (comme sur Unraid), pas de processus Node.js en production, moins gourmand en mémoire, et beaucoup plus simple à installer.

---

## 💻 1. Développer localement

Pour coder et tester tes modifications sur ton PC :

```bash
# Lancer les deux conteneurs en tâche de fond et forcer la recompilation
docker compose up -d --build

# Voir les logs en direct (optionnel)
docker compose logs -f
```

- Accède au Frontend : `http://localhost:41481` (comme en production !)
- Accède au Backend/API : `http://localhost:8000`

> **Note :** Le frontend sait automatiquement qu'il est en développement et contactera de lui-même `localhost:8000` pour ses requêtes API.

---

## 🚀 2. Publier une nouvelle version

Une fois que tu es satisfait de tes développements locaux, il est temps de packager tout ça dans l'image unifiée pour tes utilisateurs.

Un script PowerShell interactif est fourni à la racine : **`publish_release.ps1`**

### Étape par étape :
1. Assure-toi que tu as `commit` tes changements Git (recommandé).
2. Ouvre un terminal PowerShell à la racine du projet.
3. Lance le script en choisissant l'ampleur de ta mise à jour :

```powershell
# Pour une petite correction de bug (ex: 1.0.0 -> 1.0.1)
.\publish_release.ps1 -Type patch

# Pour une nouvelle fonctionnalité (ex: 1.0.1 -> 1.1.0)
.\publish_release.ps1 -Type minor

# Pour une refonte majeure (ex: 1.1.0 -> 2.0.0)
.\publish_release.ps1 -Type major
```

### Prérequis
- Être connecté à Docker Hub (`docker login`).
- Disposer de `docker buildx` avec un builder multi-architecture (Docker Desktop le fournit).
- Avoir mis à jour `CHANGELOG.md` **avant** de lancer le script : il est embarqué dans l'image et affiché dans l'application.
- Mettre à jour à la main les deux versions de secours que le script ne touche pas : `frontend/src/routes/dashboard/+layout.svelte` (badge de version) et `backend/tests/test_changelog.py`. La checklist complète est dans `release_guide.md`.

### Que fait le script ?
1. Il met à jour la version dans `frontend/package.json`, `VERSION` (racine) et `backend/VERSION`.
2. Il vérifie les fichiers de traduction (`scripts/verify_i18n.py`), y compris l'absence de texte écrit en dur dans l'interface.
3. Il vérifie la configuration de production (`scripts/verify_production_bundle.py`) : aucun port de développement ne doit rester dans le bundle.
4. Il construit `Dockerfile.standalone` (compile le Svelte, puis l'intègre au Python) pour **deux architectures** (`linux/amd64` et `linux/arm64`) avec `docker buildx`.
5. Il tague l'image avec le nouveau numéro de version et avec `latest`, et la pousse directement sur Docker Hub (`aschefr/alanbix`).

Ensuite : pousser les commits sur GitHub et créer la release (`gh release create vX.Y.Z`).

---

## 🖥️ Déployer en production (Docker Compose)

Le fichier **`docker-compose.prod.yml`** lance l'image unifiée `aschefr/alanbix:latest` (port `41481`, données dans `./data`) ainsi que SearXNG pour la recherche de jeux :

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

Pour mettre à jour une installation existante, relancer ces deux commandes : les données de `./data` sont conservées.

---

## 🧩 3. Partage sur Unraid (Community Applications)

Pour qu'Unraid affiche correctement ton application avec la belle interface, nous utilisons un modèle (Template XML).

Le modèle ne vit pas dans ce dépôt mais dans le dépôt dédié **[Aschefr/unraid-templates](https://github.com/Aschefr/unraid-templates)**, fichier **`alanbix.xml`** : c'est ce dépôt que le store Community Applications (CA) lit, avec `ca_profile.xml` pour le profil de l'auteur.

- Il contient la configuration officielle : image `aschefr/alanbix`, icône servie depuis ce dépôt GitHub (`frontend/static/favicon.png` sur `master`), port WebUI `41481`, dossier `appdata` monté sur `/app/data`.
- Tant que l'icône reste présente sur `master`, Unraid l'affichera correctement.
- À mettre à jour seulement si le port, les volumes, les variables d'environnement ou l'icône changent ; une nouvelle version de l'image ne demande aucune modification du modèle.
- Pour un test local hors store, le XML s'importe dans `/boot/config/plugins/dockerMan/templates-user/`.
