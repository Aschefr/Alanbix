# Guide de Développement et Publication (Alanbix)

Ce document explique le workflow de développement local et la procédure pour publier une nouvelle version d'Alanbix pour les environnements de production (notamment Unraid).

## 🏗️ Architecture : Dev vs Prod

Alanbix utilise deux architectures différentes selon l'environnement, afin de tirer parti du meilleur des deux mondes :

### 1. Environnement de Développement (Local)
En développement, nous utilisons l'approche classique "2 conteneurs" via `docker-compose.yml` :
- **Backend (Python/FastAPI)** : Tourne sur le port `8000`.
- **Frontend (SvelteKit/Vite)** : Tourne sur le port `8080` (en mode dev).
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

### Que fait le script ?
1. Il met à jour le fichier `package.json` du frontend et le fichier `VERSION` à la racine.
2. Il exécute le Multi-stage build du fichier `Dockerfile.standalone` (compile le Svelte, puis l'intègre au Python).
3. Il tague l'image avec le nouveau numéro de version et avec `latest`.
4. Il pousse (upload) ces images directement sur ton dépôt Docker Hub (`aschefr/alanbix`).

---

## 🧩 3. Partage sur Unraid (Community Applications)

Pour qu'Unraid affiche correctement ton application avec la belle interface, nous utilisons un modèle (Template XML).

Le fichier de référence est : **`unraid-template.xml`**

- Ce fichier contient la configuration officielle (Icône depuis GitHub, Port WebUI à `41481`, et définition du dossier de sauvegarde `appdata`).
- Tant que l'icône sur le GitHub public sera en ligne, Unraid l'affichera correctement.
- Les utilisateurs (ou toi-même) n'ont qu'à importer ce XML dans `/boot/config/plugins/dockerMan/templates-user/` pour l'installer en un clic.
