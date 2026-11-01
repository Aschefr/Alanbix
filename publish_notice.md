# Notice de publication de la mise à jour (Alanbix)

> [!IMPORTANT]
> **RÈGLE IMPORTANTE DE TRADUCTION :**
> Le fichier `CHANGELOG.md` doit **TOUJOURS** être rédigé en **anglais** (English) pour toutes les nouvelles versions, comme précisé dans `CLAUDE.md`. L'utilisation du français pour les entrées du changelog est interdite.

---

Cette notice décrit la procédure étape par étape pour mettre à jour les documents de référence, packager les nouvelles images Docker et publier la version sur GitHub et Docker Hub.

---

## 1. Fichiers à mettre à jour avant publication

### A. Fichier `VERSION`
*   Incrémenter la version selon le type de mise à jour (SemVer: Major.Minor.Patch).
*   **Fichier concerné** : `d:\Code Projects\Alanbix\VERSION`

### B. Fichier `CHANGELOG.md`
Ajouter une section pour la version `vX.Y.Z` au tout début du fichier en respectant le format standard :
```markdown
## [X.Y.Z] - YYYY-MM-DD

### Features & Bug Fixes — Title

- **Feature Name**: English description of the changes.
- **Bug Fix**: English description of the fixes.
```
*   **Fichier concerné** : `d:\Code Projects\Alanbix\CHANGELOG.md`

### C. Fichier `backend/tests/test_changelog.py` (Ligne 18)
*   Mettre à jour le fallback de version avec la version cible :
    ```python
    version = "X.Y.Z"
    ```

---

## 2. Étapes de Publication (Workflow de Release)

### Étape 1 : Modification des versions locales
1. Mettre à jour le fichier `VERSION` avec `X.Y.Z`.
2. Mettre à jour `CHANGELOG.md` en anglais comme décrit ci-dessus.
3. Exécuter la suite complète de tests backend localement pour s'assurer de l'absence de régression :
   ```bash
   cd backend
   .\venv\Scripts\python -m pytest tests/ -v
   ```

### Étape 2 : Construction et Validation de l'Image Docker Unifiée
Avant de pousser sur Docker Hub, compiler et tester localement avec les nouveaux tags :
```bash
# 1. Builder en local l'image unifiée
docker build -f Dockerfile.standalone -t aschefr/alanbix:X.Y.Z -t aschefr/alanbix:latest .

# 2. Relancer l'environnement pour valider
docker compose down
docker compose up -d --build
```
Vérifier sur [http://localhost:41481/dashboard/ai](http://localhost:41481/dashboard/ai) que l'application fonctionne toujours et répond sans latence.

### Étape 3 : Push sur Docker Hub
Une fois validé, pousser les tags de l'image unifiée :
```bash
docker push aschefr/alanbix:X.Y.Z
docker push aschefr/alanbix:latest
```

### Étape 4 : Commit, Tag & Push GitHub
Créer le tag git correspondant à la version et envoyer sur GitHub :
```bash
git add .
git commit -m "release: vX.Y.Z - Short description of release"
git tag -a vX.Y.Z -m "Version X.Y.Z - Release summary notes."
git push origin master
git push origin vX.Y.Z
```

### Étape 5 : Créer la Release GitHub
```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes "Release notes in English"
```

