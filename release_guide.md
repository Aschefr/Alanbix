# Guide de Release — Checklist Complète

Pour publier une nouvelle version d'Alanbix sur GitHub et Docker Hub sans rien oublier, suivez cette checklist dans l'ordre.

---

## 1. Rédaction & Documentation

### A. Changelog (`CHANGELOG.md`)
- [ ] Ajouter le nouveau bloc de version **en haut du fichier** sous le format :
  ```markdown
  ## [X.Y.Z] - AAAA-MM-JJ

  ### Titre de section

  - **Titre du changement** : Description claire.
  ```
  > [!IMPORTANT]
  > Le fichier `CHANGELOG.md` local doit impérativement être mis à jour **avant** de lancer le script de publication. C'est ce fichier local qui est embarqué dans l'image Docker pour l'affichage de l'historique des versions dans l'application.


### B. Documentation utilisateur (`docs/`)
Si les changements impactent une fonctionnalité documentée, mettre à jour les fichiers concernés :
- [ ] `docs/fr/features/ai-assistant.md` — Assistant IA, file d'attente, tool calling
- [ ] `docs/fr/features/tournaments.md` — Moteur de tournois
- [ ] `docs/fr/features/leaderboards.md` — Classements et distinctions
- [ ] `docs/fr/features/room-plan.md` — Plan de salle
- [ ] `docs/fr/features/chat-notifications.md` — Messagerie et notifications
- [ ] `docs/fr/features/info-page.md` — Page d'informations Markdown
- [ ] `docs/fr/features/languages.md` — Gestion des langues (i18n)
- [ ] `docs/fr/features/administration.md` — Administration et modération
- [ ] `docs/fr/quickstart.md` — Guide de démarrage rapide
- [ ] **Docs anglaises** : Mettre à jour les fichiers miroirs dans `docs/en/features/` et `docs/en/quickstart.md`.

### C. README (`README.md`)
- [ ] Si une nouvelle fonctionnalité majeure est ajoutée, l'ajouter à la liste des features.
- [ ] Si un nouveau screenshot est pertinent, l'ajouter dans `screenshots/` et le référencer.

### D. Build Guide (`BUILD_GUIDE.md`)
- [ ] Si l'architecture de build change (ports, Dockerfile, workflows), mettre à jour.

---

## 2. Bump des Versions (SemVer)

Mettre à jour la chaîne de version `X.Y.Z` dans les fichiers suivants :

| Fichier | Rôle |
|---------|------|
| `VERSION` (racine) | Version principale du projet |
| `backend/VERSION` | Version lue par le backend FastAPI (`/health`) |
| `frontend/src/routes/dashboard/+layout.svelte` | Fallback du badge de version (variable `version` dans le bloc `/health`) |
| `backend/tests/test_changelog.py` (ligne 18) | Fallback de version dans le test changelog |

> **Raccourci** : Le script `publish_release.ps1` met à jour automatiquement `VERSION`, `backend/VERSION` et `frontend/package.json`. Mais les deux derniers fichiers doivent être mis à jour manuellement.

---

## 3. Tests & Validation

### A. Tests unitaires backend
```powershell
cd backend
.\venv\Scripts\python -m pytest tests/ -v
```
- [ ] Tous les tests passent (actuellement 51 tests).
- [ ] Aucune régression.

### B. Vérification i18n
```powershell
python scripts/verify_i18n.py
```
- [ ] Pas de clés manquantes entre les fichiers de traduction.

### C. Reconstruction Docker locale
```powershell
docker compose down
docker compose up -d --build
```
- [ ] Le frontend compile sans erreur.
- [ ] Le backend démarre sans erreur.
- [ ] Navigation manuelle rapide : dashboard, assistant IA, tournois.

---

## 4. Publication

### Option A : Script automatisé (recommandé)
```powershell
# patch = X.Y.Z+1 | minor = X.Y+1.0 | major = X+1.0.0
.\publish_release.ps1 -Type patch
```
Ce script :
1. Bumpe la version dans `frontend/package.json`, `VERSION` et `backend/VERSION`.
2. Vérifie les fichiers i18n (`scripts/verify_i18n.py`).
3. Build l'image standalone (`Dockerfile.standalone`).
4. Push vers Docker Hub (`aschefr/alanbix:X.Y.Z` + `aschefr/alanbix:latest`).

### Option B : Publication manuelle
```powershell
# 1. Build
docker build -f Dockerfile.standalone -t aschefr/alanbix:X.Y.Z -t aschefr/alanbix:latest .

# 2. Push
docker push aschefr/alanbix:X.Y.Z
docker push aschefr/alanbix:latest
```

---

## 5. Commit, Tag & Push GitHub

```powershell
git add .
git commit -m "feat/fix(composant): description du changement"
git push origin master
```

---

## 6. Création de la Release GitHub

```powershell
gh release create vX.Y.Z --generate-notes
```
- [ ] Les notes de release GitHub sont cohérentes avec le `CHANGELOG.md`.

---

## Mémo : Fichiers impactés par une release typique

| Toujours modifiés | Si changement de feature | Si nouvelle fonctionnalité |
|-------------------|--------------------------|---------------------------|
| `VERSION` | `docs/fr/features/*.md` | `README.md` |
| `backend/VERSION` | `docs/en/features/*.md` | `screenshots/*.png` |
| `CHANGELOG.md` | `docs/*/quickstart.md` | `BUILD_GUIDE.md` |
| `test_changelog.py` (fallback) | | |
