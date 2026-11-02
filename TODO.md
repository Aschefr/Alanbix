# Alanbix — liste des améliorations

Bilan du 2 novembre 2026. Cochez une ligne quand elle est faite.

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
- [ ] Dans ses réponses en liste, le gras (`**Nom**`) s'affiche avec ses astérisques au lieu d'être mis en gras.
- [ ] Sa réponse prend 1 à 2 minutes avec le modèle actuel. Il faudrait essayer un modèle plus rapide, ou une machine plus puissante.
- [ ] Assistant privé : appliquer au mode streaming les mêmes corrections d'appel d'outils que dans le chat public (identifiant d'appel, arguments envoyés sous forme de texte).

- [ ] Les outils réseau de l'assistant privé (ping, traceroute, nslookup, arp) ne sont pas installés dans l'image Docker, donc ils échouent. Il faut soit les installer, soit retirer ces outils.

## Priorité 4 — Documentation

- [ ] Le README et le guide d'installation renvoient vers `unraid-template.xml`, qui n'existe pas. Il faut créer ce fichier ou retirer le lien.

## Plus tard — Entretien du code

- [ ] Découper petit à petit les fichiers trop gros, chaque fois qu'on y touche :
  - `PublicChat.svelte` et `routers/tournaments.py` font environ 3 000 lignes chacun ;
  - le tableau de bord, la page IA, les réglages admin et `ia_tools.py` en font plus de 2 000.
- [ ] Remplacer `datetime.utcnow()`, qui disparaîtra d'une future version de Python (12 endroits).
- [ ] Chercher pourquoi les tests signalent une tâche `Event.wait` lancée sans attendre sa fin.
- [ ] Passer à Svelte 5. Ce chantier a été reporté volontairement et peut attendre.
