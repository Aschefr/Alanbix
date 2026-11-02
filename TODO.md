# Alanbix — liste des améliorations

Bilan du 2 novembre 2026. Cochez une ligne quand elle est faite. Version 1.37.0 publiée le 2 novembre 2026.

## Où en est l'app

Depuis la reprise du 29 octobre 2026 :

- 219 commits et 5 versions publiées, de la 1.34.0 à la 1.36.0.
- 241 tests automatiques au vert, contre 94 au départ.
- **Sécurité :**
  - la clé qui signe les connexions n'est plus écrite dans le code ;
  - le CORS, qui décide quels sites ont le droit d'appeler l'API, est fermé par défaut ;
  - les bibliothèques sont fixées à une version précise ;
  - l'image Docker ne contient plus de base de données.
- **Traductions :**
  - les 391 textes écrits en dur sont passés en français, anglais et espagnol, avec un contrôle automatique ;
  - le bug qui figeait les traductions est corrigé.
- **Design :**
  - l'identité de l'app est décrite dans `PRODUCT.md` et `DESIGN.md` ;
  - tous les écrans ont été revus, sur ordinateur comme sur mobile.
- **@Alanbix dans le chat public :**
  - il suit la conversation et consulte les vraies données : matchs, équipes, places ;
  - c'est fait sur `dev`, mais pas encore publié.

## Priorité 1 — Sécurité et filet de sécurité

- [x] **Limiter les essais de mot de passe.** Après 5 erreurs sur un compte (ou 20 sur plusieurs comptes) depuis la même adresse en 15 minutes, cette adresse attend 5 minutes.
- [x] **Faire tourner les tests sur GitHub.** Tous les tests tournent maintenant à chaque envoi sur `dev`, `master` ou `main` (`.github/workflows/tests.yml`).

## Priorité 2 — Image Docker

- [x] Faire tourner l'app sans les droits administrateur (root). Le compte se règle avec `PUID` et `PGID`, et les anciennes installations sont reprises automatiquement.
- [x] Ajouter une vérification de santé, pour que Docker sache tout seul si l'app répond.
- [x] Retirer de l'image finale les outils de compilation : l'image installée passe de 641 à 315 Mo.

## Priorité 3 — @Alanbix

- [x] Quand il est déjà occupé (pause de 15 secondes), désactivé ou que l'IA ne répond pas, le joueur qui l'a appelé en est prévenu, au lieu d'un silence.
- [x] Dans ses réponses en liste, le gras (`**Nom**`) s'affichait avec ses astérisques : le chat public met maintenant en forme le gras, l'italique, le code et les puces.
- [ ] Sa réponse prend 1 à 2 minutes avec le modèle actuel. Il faudrait essayer un modèle plus rapide, ou une machine plus puissante (pas urgent). En attendant, chaque demande au modèle peut durer jusqu'à 5 minutes avant d'être abandonnée, au lieu de 90 à 120 secondes.
- [x] Assistant privé en streaming avec un service compatible OpenAI : les appels d'outils arrivaient en morceaux jamais recollés, donc ils plantaient. Ils sont maintenant reconstitués, avec leurs arguments et leur identifiant.

- [x] Le ping et le traceroute de l'assistant privé échouaient faute de programme dans l'image Docker : ils sont installés (+2 Mo) et fonctionnent sans root. La recherche DNS et le scan réseau n'en avaient pas besoin.

## Priorité 4 — Documentation

- [x] La doc renvoyait vers un `unraid-template.xml` qui n'est plus dans ce dépôt : elle renvoie maintenant vers le store Community Applications et vers `alanbix.xml` du dépôt `Aschefr/unraid-templates`.
- [x] `PUID=99` et `PGID=100` ajoutés à `alanbix.xml` dans le dépôt `Aschefr/unraid-templates`.

## Plus tard — Entretien du code

- [ ] Découper petit à petit les fichiers trop gros, chaque fois qu'on y touche (règle systématique : à chaque correction ou amélioration qui touche l'un d'eux, une partie en est sortie dans un fichier à part) :
  - `PublicChat.svelte` et `routers/tournaments.py` font environ 3 000 lignes chacun ;
  - le tableau de bord, la page IA, les réglages admin et `ia_tools.py` en font plus de 2 000.
- [x] `datetime.utcnow()`, qui disparaîtra d'une future version de Python, est remplacé partout (47 endroits) par `app/clock.py`.
- [x] L'avertissement `Event.wait` venait d'un test qui remplaçait `asyncio.wait_for` sans fermer la tâche : corrigé. Les tests tournent sans aucun avertissement.
- [ ] Tableau de bord, onglet « Tournois en cours » : sur un écran de 900 px de haut, l'aperçu de l'arbre déborde par-dessus le lien « Voir les tournois » (la zone de l'arbre impose 200 px minimum, alors qu'il ne reste qu'environ 95 px). Ce problème existait déjà avant Svelte 5.
- [ ] Passer à Svelte 5 (mesuré le 2 novembre 2026) :
  - étape 1, sans réécrire le code : faite sur la branche `feat/svelte5` (2 novembre 2026). Le code de l'app est plus léger de 30 % (3,0 → 2,1 Mo). Tous les écrans ont été vérifiés sur le serveur de test (ordinateur, mobile 360 px, mode sombre, langues, assistant IA, chat public, administration), sans erreur. Reste à l'utiliser quelques jours en test, puis à fusionner dans `dev` ;
  - étape 2, réécriture « runes » : 228 `$:`, 131 `export let`, 1 025 `on:`, 26 `createEventDispatcher` dans 50 fichiers (36 000 lignes). À faire fichier par fichier, en même temps que le découpage des gros fichiers.
