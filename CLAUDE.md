# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- Always read the project rules (section 9 below) before planning or writing code.
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

## 5. Maintenance de la Documentation

**Toute modification de code ou ajout de fonctionnalité doit s'accompagner d'une mise à jour de la documentation.**

- Les guides se trouvent sous `docs/fr/` (guide de démarrage, moteur de tournois, classements, plan de salle, assistant ia, messagerie, page d'infos et administration).
- Si une modification affecte des boutons, des flux utilisateur ou des configurations système, mettez à jour le fichier de fonctionnalité correspondant et assurez-vous que les captures d'écran associées dans `/screenshots` restent fidèles à l'interface.
- Le Changelog (`CHANGELOG.md`) doit **toujours** être rédigé en anglais pour les nouvelles versions.

---

## 6. Internationalisation (i18n)

**Toutes les clés de traduction doivent toujours être synchronisées et traduites dans tous les fichiers de langue (`fr.json`, `en.json`, `es.json`...).**

- Ne livrez jamais une version sans vérifier que la structure des fichiers de langue est identique.
- Exécutez systématiquement `python scripts/verify_i18n.py` pour valider l'intégrité de l'i18n avant tout commit, push ou publication.

---

## 7. Outils IA (Tool Calling) & Langue

**Utiliser l'anglais pour la définition et l'usage des outils IA, mais répondre dans la langue de l'utilisateur.**

- Les définitions d'outils, descriptions, schémas de paramètres et messages de retour JSON des outils dans `ia_tools.py` doivent être rédigés en **anglais**.
- L'IA doit toujours formuler sa réponse finale dans la langue de l'utilisateur (ex. français) et ne pas conserver la langue d'usage des outils ou de sa réflexion interne.

## 8. Publication d'une version

**Avant toute publication, lire en entier `BUILD_GUIDE.md` et `release_guide.md`, puis les suivre à la lettre.**

- L'image Docker est multi-architecture : `docker buildx build --platform linux/amd64,linux/arm64 -f Dockerfile.standalone -t aschefr/alanbix:X.Y.Z -t aschefr/alanbix:latest --push .` (comme `publish_release.ps1`). Jamais de `docker build` simple : `latest` ne fonctionnerait plus sur arm64.
- Lancer `python scripts/verify_i18n.py` et `python scripts/verify_production_bundle.py` avant la construction.
- Si la version a déjà été montée à la main, ne pas relancer `publish_release.ps1` (il la monterait une seconde fois) : exécuter ses étapes manuellement.
- Après l'envoi, vérifier avec `docker buildx imagetools inspect aschefr/alanbix:latest` que les deux architectures sont présentes, puis créer la release GitHub sur `master`.

---

## 9. Règles du projet & choix d'architecture

**Reprises de l'ancien `cahier_des_charges.yaml` (archivé dans `docs/archive/`), mises à jour.**

Règles de développement :
- **Confirmations** : jamais de `window.confirm`. La confirmation s'intègre sous l'élément cliqué (inline) ou dans une modale « glass » personnalisée.
- **Icônes** : composant `Icon` (icônes en traits) plutôt que des emojis dans l'interface. Exceptions voulues : les distinctions (awards) et les pastilles colorées de l'onglet « Conversations IA » de l'administration.
- **Mobile** : tout changement d'interface se contrôle sur téléphone (de 320 à 430 px de large), pas seulement sur ordinateur.
- **Temps réel** : l'interface se met à jour sans F5, par WebSocket ou appels API.
- **Base de données** : toute nouvelle colonne passe par une migration manuelle `ALTER TABLE` dans `init_db()` (`backend/app/database.py`).
- **Colonnes JSON SQLAlchemy** (`bracket`, `config`, `results`) : appeler `flag_modified(objet, 'colonne')` avant le commit, sinon la modification (surtout une mise à `None`) n'est pas enregistrée.
- **Assistant IA** : son prompt est construit en couches dans `backend/app/ia_prompt.py` (personnalité modifiable par l'admin, règles fixes, guide de l'application, contexte en direct). Ne pas remettre de règles ni de noms d'outils dans le texte modifiable.

Choix d'architecture à respecter :
- **SQLite** : un seul fichier, pas de conteneur de base dédié. Attention aux verrous (« database is locked ») sur des requêtes concurrentes.
- **File d'attente IA** : en mémoire Python (`asyncio`), pas de Redis. Elle est perdue au redémarrage, ce qui est acceptable pour une LAN.
- **Recherche de connaissances (RAG)** : similarité cosinus NumPy en mémoire, pas de base vectorielle. Adapté à quelques centaines de documents.
- **Production** : une seule image (API FastAPI + interface statique, port 41481), sans Node.js, qui doit rester légère en mémoire.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
