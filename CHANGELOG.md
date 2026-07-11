# Changelog

## [1.30.0] - 2026-07-11

### Features & Security — AI Admin Calls, RAG suggestions, and Real-Time Chat Sync

- **AI Admin Calls Tool & Manual Button**: Implemented the `call_admin` tool for the AI assistant and a manual "Call Admin" button for players. Added configurable anti-spam limits (cooldown period, daily user limit, global hourly limit) to prevent spam.
- **Separated Call Admin Configuration**: Split the configuration toggles so that the manual button and the AI tool calling capability can be enabled or disabled independently from the admin panel.
- **RAG Knowledge Suggestion panel**: Created a new workflow where the AI assistant can suggest additions to the RAG knowledge base. Admins can review, edit, approve, or reject suggestions directly from a newly designed "Conversations IA" section in the admin panel.
- **Multi-language Error Handling**: Modified backend cooldown verification endpoints to return structured data (`error_code` and `params`) instead of hardcoded French text. Enhanced the client API class to pass structured errors, enabling dynamic translation of cooldown limits using `$t` Svelte helper on the player's view (supporting French, English, and Spanish).
- **Notification Filtering via Active Chat Tracking**: Introduced an `/active-chat/{conv_id}` endpoint and a frontend ping interval (every 4 seconds) to track which conversation a player is actively viewing. If the player is looking at the chat window, database notifications are skipped on admin message interventions to prevent unread notification badges from flashing.
- **Real-Time WebSocket Message Deletion Sync**: Integrated WebSocket broadcasts (`ia_message_deleted`) when messages are deleted. Implemented local action locks (`isProcessingLocalAction`) on the frontend to avoid race conditions and infinite reload loops during batch message deletions.
- **AI Response Regeneration Fix**: Resolved a frontend bug where the "Retry" button on bot messages blocked the request by setting `loading = true` too early. Added support for `skip_save_user` payload flag to prevent prompt duplication in both the database and the Svelte UI during regeneration.
- **Unified Button Styling**: Replaced the default unstyled `btn-ghost` with the project-wide semi-transparent `btn-secondary` class for Dismiss (Admin calls) and Reject (RAG suggestions) actions.

## [1.29.2] - 2026-07-11

### Bug Fixes — Tournament Bracket Layout & AI Chat Context

- **Tournament Detail Sizing**: Fixed a layout bug where completed (status `DONE` or `CLOSED`) tournament bracket views and live standings collapsed in height when details were folded. Extended height-filling CSS classes (`collapsed-layout`, `split-fill`) to all non-`OPEN` tournament states.
- **AI Conversation Context Continuity**: Fixed a bug where the first kept message in the active history was systematically omitted after context truncation or compression. Changed the strict inequality (`>`) comparison operator to non-strict (`>=`) for `compressed_at` timestamp filtering in both the backend database queries and frontend Svelte state calculations.
- **AI Multi-Step Tool Calling**: Fixed an issue where the model lost context or returned generic clarification questions when follow-up queries required secondary tool calls. Corrected the tool-popping condition in `ia_queue.py` to allow multi-step tool calls up to `max_tool_rounds` (3 rounds) instead of disabling tool calls immediately after the first step.
- **AI Stream Chunk Buffering**: Fixed an issue where the streamed AI responses were frequently cut off, truncated, or incomplete. Resolved a classic stream-splitting bug in `+page.svelte` by implementing proper line-buffering to process incomplete JSON chunks at TCP package boundaries instead of discarding them.
- **SQLite WAL Mode on Windows Docker Mounts**: Fixed `OperationalError: unable to open database file` errors occurring during tool executions. Switched the SQLite journal mode from `WAL` (which uses shared memory `mmap` that is unsupported by Docker/VirtioFS mounts on Windows hosts) to `DELETE` mode.

## [1.29.1] - 2026-07-11

### Features & Refactoring — Modal Dialog Styling and Accessibility (a11y)

- **Modal Styles Unification**: Centralized CSS properties for modals, overlay dialogs, and cards into the global stylesheet (`app.css`) using `.modal-overlay-global` and `.modal-card-global` to reduce redundancy.
- **Keyboard Accessibility (a11y)**: Added global keyboard event listeners for the `Escape` key to instantly dismiss all active modal dialogs, alongside ARIA accessibility attributes (`role="dialog"`, `aria-modal="true"`, `aria-label="Close"`).
- **Accidental Close Protection**: Upgraded all modal overlays to track `mousedown` and `mouseup` events separately. This prevents overlays from closing automatically when text selections drag out of the modal card area.

---

## [1.29.0] - 2026-07-11

### Features & Bug Fixes — Tournament Registration, UI Layout, and Team Selection

- **Tournament Unregistration**: Added the ability for registered players to unregister themselves from `OPEN` tournaments. This action includes an inline confirmation dialog ("Se désinscrire ? ✓ / ✕") to avoid accidental leaves, and automatically removes the player from any registered team for that tournament.
- **Rules Card Overlay Fix**: Moved the tournament rules panel (`.hero-rules`) from the bottom-right corner to the top-right corner to resolve a visual overlap with the "S'inscrire" / "Se désinscrire" button. Also removed `backdrop-filter: blur()` from rules panels to optimize GPU rendering.
- **Welcome Wizard Team Buttons**: Introduced clickable button selectors for existing teams under the team name input field in the welcome wizard and profile page, making team selection more explicit and intuitive.
- **Dynamic LAN Event Name**: Replaced the hardcoded wizard welcome title with a dynamic greeting displaying the custom LAN event name configured by administrators (`Bienvenue à l'évènement {eventName} !`).
- **Autocompletion Cleanup**: Removed native browser input autocompletion datalists for team names to prevent visual overlap with the newly added team buttons.

---

## [1.28.0] - 2026-07-10

### Features — OpenAI API Compatibility & Auto-detection

- **OpenAI API Integration**: Migrated the AI backend communication model to support standard OpenAI-compatible API endpoints (`/v1/chat/completions` and `/v1/embeddings`), enabling seamless integration with LM Studio, llama-server, KoboldCPP, vLLM, and other standard LLM runners in addition to native Ollama.
- **Protocol Auto-detection**: Implemented automated API protocol detection during instance health checks and model listings. The system dynamically adjusts JSON payload structures, parameter keys, and chunk parsing mechanisms between native Ollama and OpenAI SSE streaming.
- **Startup Translation Cleanup Migration**: Added a startup migration to clean up outdated default translation overrides (`admin_settings_ai_instances` / `admin_settings_ai_instances_sub`) in user-modified data files. This automatically updates labels for instances to reflect the new OpenAI compatibility without affecting other customizations.
- **Synchronized i18n Labels**: Updated and synchronized instance configuration headings and descriptions across French, English, and Spanish translation dictionaries (`fr.json`, `en.json`, `es.json`) preserving UTF-8-sig encoding.

---

## [1.27.1] - 2026-07-10

### Features & UI — Room Plan and Dashboard UI Improvements

- **Tournament Tabs Stability**: Fixed a visual regression where active tournament tabs (`.running-tabs`) in the dashboard could disappear vertically upon click. Added `flex-shrink: 0` and a minimum height to stabilize the layout.
- **Leaderboard Avatar Protection**: Prevented visual compression of avatars (`.lb-avatar`) and rank badges (`.lb-rank`) by very long usernames in the dashboard leaderboard by forcing `flex-shrink: 0`. Long usernames are properly truncated with an ellipsis.
- **Team Names in Welcome Wizard**: Added dynamic and scaled (`textLength` / `lengthAdjust`) team name rendering on occupied seats in the simplified room plan shown during the welcome wizard.
- **Teammate Seat Coloring**: Implemented a distinctive orange/amber color scheme (`--map-seat-teammate-fill` / `--map-seat-teammate-stroke`) for seats occupied by teammates across all room plan views (full map, dashboard mini-map, and welcome wizard). The map legend dynamically updates to include teammates if the user has a team.
- **Teammates i18n Keys**: Added and synchronized the `map_legend_teammates` translation key in `fr.json`, `en.json`, and `es.json` (preserving UTF-8-sig encoding) for correct teammate seat rendering labels.

---

## [1.26.7] - 2026-07-10

### Features — Tournament Detail Hiding for All Players & Expandable Standings Team Members

- **Unified Hiding Behavior**: Broadened tournament details collapsing state persistence (via local storage) so that it is processed and respected for all connected player roles, not just administrators.
- **Expandable Team Standings**: Added the ability to expand team rows in both live and final standings views. When clicked, team rows reveal their member lists alongside their exact points details, inheriting placement, score bonus, and participation stats from their parent team instead of returning empty points.

---

## [1.26.6] - 2026-07-10

### Features — UX Création Tournoi & Rafraîchissement Réactif des Jeux

- **Mise à jour réactive de la liste des jeux** : La création d'un nouveau jeu depuis l'assistant de création de tournoi (vue *Tournois*) recharge désormais instantanément la liste des jeux disponibles sans forcer l'utilisateur à recharger la page.
- **Auto-sélection intelligente** : Le nouveau jeu créé est dorénavant automatiquement pré-sélectionné dans la liste déroulante du formulaire après validation, améliorant l'expérience utilisateur et éliminant une étape manuelle superflue.

---

## [1.26.5] - 2026-07-10

### Bug Fixes — Clé de traduction manquante dans l'administration

- **Correction i18n dash_stat_new** : Ajout de la clé de traduction manquante `dash_stat_new` dans les dictionnaires `fr.json`, `en.json` et `es.json` (encodage UTF-8-sig préservé) pour afficher correctement le statut "NOUVEAU" dans l'administration des conversations.

---

## [1.26.4] - 2026-07-09

### Features — Améliorations UX (Attente IA & Expansion des Notifications)

- **Restauration de l'indicateur d'attente IA** : L'état d'avancement de la réflexion du bot et le chronomètre de calcul sont maintenant correctement restaurés et continuent de tourner en direct si l'utilisateur quitte la page de discussion et y revient pendant le calcul.
- **Expansion Sélective des Notifications** : Les cartes de notification ne sont cliquables pour se déplier/replier que si leur longueur de texte dépasse 140 caractères. Les notifications courtes ne déclenchent plus l'effet visuel de pointeur et restent statiques.
- **Ajustement Visuel des Notifications Lues** : Opacité des notifications lues adoucie à `0.85` (au lieu de `0.7`) pour garantir un excellent confort de lecture tout en gardant une légère distinction.
- **Régulation Multilingue de la longueur des Annonces IA** : Ajustement des descriptions de schémas de tools en anglais pour ordonner au LLM de formuler des messages d'alertes directs, brefs et limités à 250 caractères maximum, dans la langue d'origine utilisée par l'utilisateur.

---

## [1.26.3] - 2026-07-09

### Bug Fixes — Robustesse du Store Page SvelteKit

- **Résilience du Store Page SvelteKit** : Ajout de guards de sécurité (`$page?.url?.pathname`) dans le layout racine pour éviter un crash Javascript (page blanche) lors de l'initialisation asynchrone des composants après déploiement.

---

## [1.26.2] - 2026-07-09

### Bug Fixes — Cache-Control & Correctifs Déploiement

- **Gestion Optimale du Cache (Zéro CTRL+F5)** : Ajout d'en-têtes de cache fins sur la route de distribution SPA. Le fichier `index.html` est servi avec `no-cache, must-revalidate` (toujours rafraîchi pour charger les nouveaux assets après mise à jour), tandis que les fichiers JavaScript/CSS hashés de SvelteKit bénéficient d'un cache longue durée (`immutable`).

---

## [1.26.1] - 2026-07-09

### Bug Fixes — File d'attente d'Auto-Titrage IA & Corrections Stabilité

- **Intégration Queue d'Auto-Titrage** : Enregistrement correct des tâches d'auto-titrage en tâche système de priorité arrière-plan (`priority=20`) dans le gestionnaire de file d'attente IA global.
- **Résolution du blocage (Regression)** : Correction d'une collision de portée de variable Python (`UnboundLocalError` sur `queue_manager`) dans la route `/ia/stream` qui bloquait le streaming des réponses de l'assistant.
- **Suppression du Code Mort** : Retrait de l'ancien endpoint direct `POST /ia/auto-title/{conv_id}` qui contournait la file d'attente d'Ollama et générait des contentions de GPU.
- **Protection Race-Condition** : Ajout d'une vérification à l'écriture pour s'assurer que l'auto-titrage n'écrase pas un titre personnalisé saisi manuellement par l'utilisateur pendant l'attente en queue.
- **Couverture de Tests Unitaire accrue** : Ajout de 4 nouveaux tests unitaires validant la limite de concurrence par GPU, le routage interne de la queue, la protection contre les réinscriptions et la gestion des titres manuels (51/51 tests au vert).

---

## [1.26.0] - 2026-07-09

### Features — Performance Mode IA & Suivi Présence Joueurs

- **Option A (Optimisé - Intercept)** : Résolution de la latence de l'assistant IA avec streaming immédiat et interception à la volée des tool calls Ollama (latence réduite de 30s à moins de 2s).
- **Titrage Gemma Robuste** : Passage à l'API `/api/generate` (Ollama) pour corriger les réponses tronquées et intégration de la détection multilingue dynamique des titres par défaut.
- **Suivi Présence 100% Mémoire** : Tracker en mémoire vive (`ACTIVE_USERS`) évitant les verrous de base de données SQLite et assurant un site fluide.
- **Point Vert de Présence** : Visualisation en temps réel de l'état de connexion ("En ligne") sur les avatars (dans l'annuaire des joueurs et l'en-tête de chat) ainsi que dans l'administration (avec wrapper Svelte pour éviter toute coupure ou troncature visuelle).
- **Support i18n Complet** : Traduction dynamique de l'état "En ligne" en français, anglais, et espagnol.

---

## [1.25.4] - 2026-07-09

### Bug Fixes — AI Chat Takeover & i18n Translation Tasks

- **Dynamic Admin Override Updates**: Configured the player AI chat interface to immediately toggle the "Admin Override / Takeover" banner when the admin takes or hands back control, without requiring a page refresh (F5). Broadcasts a WebSocket message (`admin_override_updated`) from the backend when overridden, which Svelte listens to live.
- **Translation Queue Visibility**: Registered bulk translation tasks in the global `ia_queue` manager. Bulk translation runs now correctly appear in the active tasks section of the Admin Settings & AI Queue page in real-time, notifying the dashboard of status changes.

---

## [1.25.2] - 2026-07-09

### Bug Fix — Tournament Team Building

- **Fixed Hidden Team Composition for New Tournaments**: Restored visibility of detail sections (info cards, participant pool, team builder) for tournaments in `OPEN` status. A previous change (v1.23.1) made all detail sections conditional on the `showDetails` toggle, but the toggle button was only rendered for `RUNNING`/`DONE`/`CLOSED` statuses — causing `OPEN` tournaments to have everything hidden with no way to toggle it back when localStorage had `showDetails=false`.

---

## [1.25.0] - 2026-07-08

### Features & UI — Room Layout Editor

- **Toolbar Styling Harmonization**: Standardized height, font size, padding, and borders across all buttons and selects in the room editor toolbar. Replaced default browser select elements with modern custom SVG arrow indicators.
- **Creation-Only Collision Avoidance**: Integrated an axis-aligned bounding box (AABB) collision detection system that automatically shifts newly added tables, seats, and furniture on creation if they would overlap with existing items.
- **Seat-Specific Collision Filtering**: Refactored seat collision checks so that seats are only evaluated against other seats. This allows seats to be successfully added on top of tables without being shifted away by table collision footprints.
- **Unrestricted Dragging & Resizing**: Dragging and resizing actions remain completely free and non-blocking, ensuring full usability of the layout and restoring functionality to resizing handles.
- **Inline SVG Delete Confirmation**: Added an inline warning overlay inside the table SVG box with confirmation ✓ and cancel ✕ controls positioned clearly above the table at the top-right (preventing overlaps and click blockage behind seats).
- **Cascade Seat Deletion**: Deleting a table now automatically removes all associated seats and unassigns seated users via backend API callbacks.
- **Direct Seat Addition & Reflowing**: Rendered a green circular "+" button as a ghost seat preview at the next vacant grid space on the table. Configured the layout grid scanner (`findFirstFreeSlot`) to skip already occupied absolute positions, ensuring correct seat reflowing and preventing seat overlapping when tables are resized.
- **Intelligent Sequential ID Re-use**: Configured tables, seats, and furniture to automatically scan and occupy the lowest available numerical gap in names (e.g. recreating Table 3 or Seat 2 if they were deleted) rather than always incrementing past the maximum index.
- **Coordinated Seat Rotation**: Configured associated seats to automatically track the table's orientation and center point during user rotation, rotating along a perfect 2D arc.
- **Dynamic Viewport Centering & Auto-Focus**: Replaced hardcoded boundaries in the "Recentrer" button (`resetView`) with a bounding box calculation of all active layout components. Focused elements are centered on initial load with a tight, optimal padding of `15px`.
- **Spectator Map Reactivity & Padding**: Fixed Svelte compiler dependency tracing on the spectator layout map by explicitly passing `allUsers` to `getOccupant`, ensuring occupied/free seat counts and avatars update live via WebSockets. Reduced margins to `15px` to match the editor.
- **Key Tracking for Instant Removals**: Appended unique keys `(id)` to the Svelte `{#each}` loops for tables, seats, and furniture. This resolves Svelte's index-based DOM recycling, causing deleted seats to vanish instantly instead of making remaining seats slide weirdly across the map coordinates.

## [1.23.1] - 2026-07-08

### Bug Fixes — Tournament Standings & UI

- **Fixed Points Distribution & Final Standings**: Aligned the final standings calculation on tournament close with the live standings projection (`_compute_projected_standings`). This resolves the issue where only the top 3 players on the podium were shown, and all other participants/teams were incorrectly listed individually with `0 pts` (due to an ID mismatch between user IDs and team IDs).
- **Fixed Premature Tournament DONE State**: Corrected the tournament completion detection in the backend to ensure that both scores of the final match are entered and different before marking a tournament as `DONE`, preventing premature UI updates and admin panel disruption when entering only the first score of the finals.
- **Frontend Detail Section Collapsing**: Modified the tournament details, registered player pool, and team composition sections to strictly respect the `showDetails` toggle state across all tournament statuses (`RUNNING`, `DONE`, `CLOSED`). The "Show Details" button now remains active and functional in all states.

---

## [1.23.0] - 2026-07-06

### Features — AI Assistant & Network Diagnostics

- **Client-side Network Diagnostics (Option 5)**: Enabled the AI assistant to perform network diagnostics (`ping_host`, `traceroute_host`, `dns_lookup`, `scan_local_network`) directly from the user's browser, overcoming the network isolation limitations of Docker containers.
  - **Asynchronous Tool Execution**: Converted the backend `execute_tool` logic to an async pipeline to support waiting for browser client responses.
  - **Client Tool Callback Integration**: Pushes a new SSE signal (`client_tool_call`) with parameters and a unique `call_id` to trigger SvelteKit actions.
  - **New API Endpoint**: Added `POST /ia/client-tool-response/{call_id}` to resolve pending diagnostics securely.
  - **SvelteKit Integration**: Implemented `runClientTool()` in Svelte which performs parallel HTTP and HTTPS probes (to bypass router filters/drops), Cloudflare DNS-over-HTTPS queries, and returns raw latency and status data.
  - **Automated Tests**: Created `backend/tests/test_network_diagnostics.py` verifying full async flow, correct responses for existing hosts (e.g. `192.168.22.1`), and timeouts/failures for offline ones (e.g. `192.168.30.100`).

---

## [1.22.0] - 2026-07-06

### Features — Administration & Games

- **Unified Admin View**: Merged the separate "Games Library" tab into the main "Tournaments & Games" tab. The tournaments list and the games gallery are now vertically stacked, providing a single cohesive page.
- **Inline Game Addition**: Organizers can now add new games directly from Step 1 of the tournament creation wizard via a `➕` button. The newly created game is automatically selected without clearing other form fields.
- **Integrated WYSIWYG Editor for Rules**: Replaced plain text areas for rules with the `EasyMDE` rich Markdown editor in both the **Add Game** modal and the **Edit Game** modal. Added responsive layout wrapping and visual theme overrides for dark mode.
- **Aesthetic Improvements**:
  - Point distribution labels (Gold, Silver, Bronze, Participation, and Bonus/Score) are now aligned horizontally on a single row using a flexbox layout, with `white-space: nowrap` to prevent text wrapping.
  - Section titles within the edit modal are now flex-aligned with their emojis.
- **New Point Allocation Defaults**: Updated default points values for new tournaments to match the new custom defaults: Winner (1.5), Second (1.3), Third (1.0), Participation (1.0), and Match/Goal Bonus (0.5).
- **Customizable SearXNG Search Engine**: Organizers can now configure their own self-hosted SearXNG instance URL for game cover searches directly in the Administration settings.
  - Added a **Test Validity** button to ensure the configured instance is reachable and supports JSON output format.
  - By default, the search engine URL is set to an empty string (`""`) for private and secure-by-default operation.
- **Dynamic Browser Tab Titles**: The browser tab title now displays the name of the LAN (configured by the admin as `event_name`) followed by the currently open page name (e.g., `Alanbix LAN - Tournois` or `Alanbix LAN - Mon Profil`).
  - Tab titles are automatically translated in real-time according to the selected user language.
  - Dynamic subpages (such as individual tournament pages) update the title automatically with their specific names (e.g., `[LAN Name] - [Tournament Name]`).
  - The administration panel dynamically appends the currently active tab (e.g., `[LAN Name] - Administration - Gestion Joueurs`).
  - Updates to the LAN name propagate instantly across all active tabs in real-time when changed by an admin.

### Maintenance & Bug Fixes

- **Unit Test Stability**: Added a `pick_instance` mock in translation unit tests to bypass the 503 error caused by empty test databases, ensuring `pytest` suites execute successfully in clean environments.
- **Backend VERSION Alignment**: Aligned the backend `VERSION` file with the root version (`1.21.0`) and cleared parity BOM markers that were causing tests to fail.

---

## [1.21.0] - 2026-07-05

### Features — AI Chat

- **Message timestamps**: Each AI assistant and user message now displays the time it was sent. Timestamps on user bubbles are rendered in a lighter color for readability.
- **Conversation auto-naming v2**: The automatic naming now uses up to 6 messages (3 user + assistant exchanges) instead of only the first user message, producing significantly more meaningful titles. The trigger still fires after the first response, using whatever context is available.
- **Manual conversation rename**: A ✏️ rename button now appears on hover over each conversation in the sidebar. Clicking it opens a rename modal with a text field (Enter to confirm) and an **AI Suggestion** button.
- **AI title suggestion — fire-and-forget via queue**: Clicking "AI Suggestion" returns immediately (`{status: "pending"}`) and routes the generation through the `IAQueueManager` as a `title_suggestion` task (priority 5, between admin and player). The result is pushed back to the frontend via WebSocket (`title_suggestion_ready`), making the task visible in the queue panel and properly coordinated with chat requests. No more HTTP blocking on Ollama.
- **New API endpoints**:
  - `PATCH /ia/conversations/{id}/title` — manual rename with broadcast
  - `POST /ia/conversations/{id}/suggest-title` — async suggestion enqueued via IAQueueManager
- **New queue task type**: `title_suggestion` added to `ia_queue.py` with dedicated `_process_title_suggestion()` method and WebSocket result broadcast.
- **i18n**: 7 new translation keys (`ai_tooltip_rename`, `ai_rename_modal_title`, `ai_rename_placeholder`, `ai_rename_suggest`, `ai_rename_suggesting`, `ai_rename_save`, `ai_rename_cancel`) added to all 6 locale files (fr/en/es × static/data).

### Bug Fixes

- **Retry pipeline**: Fixed a broken response pipeline after the "Retry" button was clicked — the response was silently lost due to a missing `full_response` propagation in the SSE event generator.
- **Ghost message on restart**: Fixed a bug where the `firefox` user account received a duplicate AI message containing the current time on every backend restart, caused by an orphaned system prompt entry in the database.
- **`api.patch()` missing**: The `api.ts` helper was missing the `patch` method, causing the manual rename save button ("Renommer") to silently fail. Added `patch` alongside the existing `put`, `post`, `delete` methods.

### Architecture

- **Queue integration for background AI tasks**: Title suggestion is now a first-class `IAQueueManager` entry, using `user_id=0` (system task) and `priority=5` to avoid the per-user queue limit while still being processed in order behind active chat requests.

---

## [1.20.0] - 2026-07-05

### Features — AI Assistant

- **High-Priority AI Tools**: Implemented 4 new high-priority tools for the AI assistant (`get_live_matches`, `get_team_roster`, `get_player_match_history`, and `get_awards`).
- **Medium-Priority AI Tools**: Implemented 4 new medium-priority tools for the AI assistant (`get_upcoming_matches`, `get_files`, `get_player_rank_progression`, and `get_bracket_detail`).
- **Fuzzy Name Matching**: Added orthographic error tolerance using `difflib` so that user queries about players, teams, tournaments, and games are accurately resolved even with spelling mistakes.
- **Robust Automated Tests**: Created `backend/tests/test_ia_tools.py` containing comprehensive unit tests verifying the correctness of all AI tools and fuzzy matching logic.

## [1.19.0] - 2026-07-05

### Améliorations — Assistant IA

- **Refonte de la personnalité d'Alanbix** : Le prompt système a été entièrement restructuré en 4 sections claires (`=== IDENTITÉ ===`, `=== CONTEXTE ===`, `=== STYLE ===`, `=== RÈGLES ===`). L'IA adopte désormais une personnalité gauloise assumée (clin d'œil à Astérix), un ton de copain passionné plutôt que d'assistant corporate, et est moins focalisée sur le coaching stratégique.
- **Refonte du prompt de clôture de tournoi** : Le `tournament_closing_prompt` est réécrit dans un style de commentateur gaulois enthousiaste — métaphores de sangliers, potions magiques, menhirs — avec humour et sarcasme.
- **Éditeur de prompt système** : Ajout d'une modale d'édition plein écran accessible depuis le panneau Administration > IA. La modale offre une grande zone de texte monospace pour éditer le prompt, un panneau de guide avec 4 blocs cliquables (Identité / Contexte / Style / Règles) et boutons « Insérer le bloc », ainsi qu'un panneau de conseils pour les nouveaux administrateurs.
- **25 nouvelles clés i18n** (`admin_prompt_modal_*`) ajoutées dans les fichiers `fr.json`, `en.json` et `es.json` (couches `static/i18n/` et `data/i18n/`).
- **Documentation IA** : Création de `docs/ia_improvements.md` listant 14 suggestions d'améliorations futures pour l'assistant (nouveaux outils de lecture et d'écriture).

### Améliorations — Internationalisation (i18n)

- **Indicateur de traduction modifiée** : Dans la page d'administration des langues, un badge visuel ("Modifié") indique désormais à l'administrateur quelles clés de traduction ont été personnalisées et s'écartent des valeurs par défaut fournies par l'application.
- **Restauration des valeurs par défaut** : Ajout d'un bouton de restauration (↺) permettant de rétablir instantanément la valeur d'usine d'une clé de traduction spécifique sans affecter le reste de la personnalisation.
- **Nouvelles clés i18n** (`admin_languages_custom_indicator`, `admin_languages_custom_tooltip`, `admin_languages_restore_tooltip`) intégrées de base dans les 3 langues.

## [1.17.10] - 2026-06-20

### Maintenance & CI/CD

- **Changelog Updates**: Corrected the application changelog formatting and visibility.
- **Strict Translation Verification (i18n)**: Enhanced the verification script to perform exhaustive checks across all translation JSON files, ensuring perfect key synchronization, absence of empty translations, and whitelist/blacklist controls for emojis.
- **Docker Release Safeguard**: Integrated the verification check into the build script to prevent publishing incomplete translation files to Docker Hub.
- **GitHub Actions Workflow**: Added CI checks on pushes and pull requests to enforce translation consistency and synchronization automatically.

## [1.17.9] - 2026-06-20

### Maintenance

- **Release fixes**: Re-released verification tooling fixes.

## [1.17.8] - 2026-06-19

### Améliorations & Corrections de bugs

- **Optimisation de la vue Spectateur & Dashboard** : Harmonisation des vues de brackets. Pour le Double Élimination, le Winner Bracket et le Loser Bracket sont maintenant affichés en couches distinctes (empilés verticalement sur la vue Spectateur) afin de prévenir la compression horizontale sur les résolutions standards.
- **Lisibilité en mode Spectateur** : Le format Round Robin dispose d'un fond de carte contrasté semi-transparent et de textes blancs à fort contraste pour rester parfaitement lisible au-dessus des arrière-plans cinématiques de jeux. Le format FFA a été revu avec une disposition fluide (`flex-wrap`) et dynamique (hauteur `fit-content`) qui élimine tout grand espace vide superflu entre les manches.
- **Sécurité et Robustesse de saisie de scores** : Le backend rejette désormais toute soumission de score de match contenant un joueur TBD (ID 0) afin d'éviter la corruption des brackets. Les scores saisis sont fusionnés intelligemment avec les scores existants pour prévenir les conditions de concurrence et les écrasements accidentels.

## [1.17.7] - 2026-06-19

### Améliorations

- **Identification visuelle du joueur dans le bracket** : Le pseudo du joueur connecté (ou le nom de son équipe en mode équipes) est désormais mis en surbrillance dans l'arbre de tournoi avec un fond bleu accent et une bordure latérale distinctive. Le highlight est adapté aux deux modes clair/sombre et fonctionne dans tous les formats de bracket (Single/Double Élim, Round Robin, FFA).

## [1.17.6] - 2026-06-19

### Corrections de bugs

- **Saisie de score sur match TBD** : Correction d'un bug permettant à un joueur en attente d'adversaire (TBD) de saisir et valider un score. Les champs de saisie sont désormais masqués et le backend rejette toute tentative de soumission de score sur un match dont l'adversaire n'est pas encore déterminé.

## [1.17.5] - 2026-06-19

### Corrections de bugs

- **Modales Non-Intrusives (G-08)** : Remplacement de l'utilisation de `window.confirm` par une modale de confirmation inline lors de l'annulation d'une manche FFA.
- **Robustesse des tests unitaires** : Correction des tests unitaires i18n suite à l'introduction de la séparation des répertoires de traduction en environnement de production et de données utilisateur.

## [1.17.4] - 2026-06-19

### Corrections de bugs

- **Persistance des illustrations de jeux (Docker)** : Les images de couverture des jeux étaient stockées dans un dossier éphémère du conteneur (`/app/static/uploads/games/`) et disparaissaient à chaque redémarrage ou mise à jour Docker. Elles sont désormais stockées dans le volume persistant `/app/data/game_images/`. Une migration automatique au démarrage déplace les fichiers existants et met à jour les chemins en base de données.

### Maintenance

- **Nettoyage de sécurité pour la release** : Retrait des fichiers `.bak` du dépôt Git, ajout de `test_api.py` et `*.bak` au `.gitignore` pour éviter l'inclusion de fichiers de développement ou de sauvegarde dans les releases publiques.

## [1.17.3] - 2026-06-19

### Améliorations & Corrections de bugs

- **Mutualisation de la modale d'édition des tournois** : Création d'un composant unique réutilisable `EditTournamentModal.svelte` et suppression de la duplication de code entre les pages tournois joueurs et administration.
- **Correction sur le Plan de Salle** : Résolution d'un bug d'affichage qui affichait l'expression ternaire JavaScript brute au lieu de la traduction dynamique correcte lorsque le joueur n'avait pas de siège. Simplification et uniformisation des instructions de navigation en "Clic pour naviguer." dans les langues supportées.
- **Traduction de la page Assistant IA** : Extraction et localisation des 14 phrases de chargement gauloises et du titre par défaut des conversations dans les fichiers i18n (`fr.json`, `en.json`, `es.json`) ; mise à jour du backend pour supporter les détections d'auto-titre sur les titres par défaut traduits.
- **Redimensionnement dynamique et cohérent de la Sidebar** : Détection automatique en JavaScript du retour à la ligne des libellés de navigation de la barre latérale, avec réduction uniforme de la taille de police (jusqu'à `0.75rem`) pour éviter les retours à la ligne inesthétiques tout en conservant une cohérence visuelle parfaite.

## [1.17.2] - 2026-06-19

### Corrections de bugs & Internationalisation (i18n)

- **Résolution du mix de langues (français/espagnol)** : Remplacement de tous les textes codés en dur en français par des appels réactifs `$t(...)` dans le composant de gestion des tournois.
- **Support complet de la pluralisation espagnole** : Correction dynamique du suffixe de pluriel pour "Jugador" (qui passait de "Jugador" à "Jugadors") pour afficher correctement "Jugadores" en espagnol en fonction du store de langue active (`currentLang`).
- **Synchronisation globale des fichiers de langues** : Mise à jour et alignement des clés manquantes dans `fr.json`, `en.json` et `es.json` tant dans la configuration d'usine (`static/i18n`) que dans les surcharges utilisateur (`data/i18n`).

## [1.17.1] - 2026-06-18

### Nouvelles fonctionnalités

- **Seeding automatique des fichiers de langue au démarrage** : Copie automatique des fichiers d'usine (`fr.json`, `en.json`, `es.json` complet) dans le dossier de données de l'utilisateur (`data/i18n/`) s'ils n'existent pas encore, pour faciliter la prise en main et la personnalisation par l'utilisateur.

### Corrections de bugs

- **Chargement dynamique des langues modifiées** : Correction de l'application Svelte pour charger dynamiquement les fichiers i18n depuis l'API de fusion `/api/i18n/{lang}` au lieu de `/static/i18n/`, permettant de prendre en compte immédiatement les modifications locales ou de nouvelles langues (comme l'espagnol).
- **Ajustement de la hauteur d'affichage (Viewport Scroll)** : Correction de la hauteur des conteneurs pour éliminer les barres de défilement externes indésirables sur la page d'administration des langues en forçant `.container` et `.lang-page` à 100% de la hauteur disponible.
- **Sécurité et filtrage des langues** : Interdiction d'utiliser ou de l'ister les routes réservées de l'API (comme `bulk-translate` ou `auto-translate`) comme codes de langue valides et suppression des fichiers correspondants.

## [1.17.0] - 2026-06-18

### Nouvelles fonctionnalités

- **Système d'internationalisation complet (i18n)** — Mise en place d'une architecture multilingue intégrale pour l'application :
  - **Store réactif Svelte** (`i18nStore.ts`) : Chargement asynchrone des traductions depuis l'API, sélection de la langue avec persistance `localStorage`, helper `$t()` avec interpolation de variables (`{name}`, `{count}`), et mapping des drapeaux par code langue.
  - **Backend i18n** (`/api/i18n`) : Endpoints CRUD complets pour la gestion des langues (GET, POST, PUT, DELETE), avec système de merge bicouche (`static/i18n/` ← fichiers livrés, `data/i18n/` ← éditions utilisateur).
  - **Traduction automatique par IA** : Endpoint dédié utilisant la file Ollama pour traduire les clés i18n d'une langue source vers une langue cible, avec nettoyage automatique du markdown et des guillemets parasites.
  - **Fichiers de langue** : `fr.json` (850+ clés), `en.json` (traduction complète), support de nouvelles langues (ex: `es.json`).
- **Page d'administration des langues** (`/dashboard/admin/languages`) — Interface complète de gestion des traductions :
  - **Éditeur bicolonne** : Vue côté-à-côté de la langue de référence et de la langue cible, avec catégorisation automatique par préfixe de clé (Sidebar, Dashboard, Tournois, IA, etc.).
  - **Navigation par catégories** : Barre latérale avec compteurs de clés manquantes par catégorie et badge de progression.
  - **Traduction individuelle & en masse** : Bouton de traduction IA par clé, traduction en lot (toutes les clés ou seulement les vides), avec barre de progression et bouton d'annulation.
  - **Recherche et filtrage** : Recherche instantanée dans les clés, valeurs source et cible.
  - **Persistance des catégories repliées** : L'état de collapse des catégories est sauvegardé en `localStorage`.
  - **Toasts de confirmation** : Feedback visuel pour toutes les actions (sauvegarde, suppression, synchronisation, traduction).
  - **Modales de confirmation inline** : Confirmations de suppression de langue via popover sous le bouton (sans titre, Valider/Annuler) avec fond opaque, conformément aux règles du projet.
- **Synchronisation des clés manquantes** — Détection et ajout automatique des clés absentes d'un fichier de langue par rapport à la référence (`fr.json`) :
  - **Distinction clés absentes vs non-traduites** : Nouveau compteur `structuralMissingCount` différenciant les clés manquantes du fichier (🔑 rouge) des clés présentes mais vides (⚠️ orange).
  - **Bandeau d'alerte** : Notification visuelle rouge lorsque des clés structurelles sont manquantes (typiquement après une mise à jour de l'app), avec explication et bouton de synchronisation intégré.
  - **Endpoint `/api/i18n/{lang}/sync`** : Ajout des clés manquantes avec valeurs vides, retour du nombre de clés ajoutées.
- **Optimisation i18n — Regroupement des doublons** : Factorisation des clés de traduction dupliquées pour réduire la taille des fichiers de langue.
- **Sélecteur de langue dans le menu** : Nouveau dropdown de sélection de la langue dans la barre latérale du dashboard, avec drapeaux emoji et persistance du choix.

### Corrections de bugs

- **Accès aux boutons inline après blocage IA** : Correction d'un bug permettant aux joueurs bloqués par l'IA de continuer à accéder aux boutons d'action dans les conversations.
- **Synchronisation des clés ES** : Correction du backend qui retournait une erreur 404 pour les langues avec un fichier vide (`{}` est falsy en Python). La condition a été corrigée de `not target_data` à `target_data is None`.
- **Prompt de tournois localisé** : Déplacement du prompt système IA des tournois dans les fichiers i18n pour permettre sa traduction.
- **Éditeur d'image de profil** : Correction de la sauvegarde du crop/zoom/couleur de fond et réouverture du modal à l'édition au lieu d'un prompt de fichier.

## [1.16.2] - 2026-06-14

### Corrections de bugs

- **Historique des versions (Docker Hub / Unraid)** : Correction de la séquence de copie dans le `Dockerfile.standalone` qui provoquait l'écrasement du `CHANGELOG.md` par un fichier vide temporaire lors de la génération de l'image de production.

## [1.16.1] - 2026-06-14

### Corrections de bugs & Résilience

- **Résilience de démarrage (Redirect Loop)** : Résolution d'une boucle infinie de redirection clignotante entre la page de connexion et le tableau de bord en cas de serveur injoignable, hors ligne ou en cours de redémarrage.
- **Écran de chargement unifié** : La page de connexion reste sur l'écran de chargement avec le logo animé tant que la vérification de session n'est pas finalisée, évitant tout clignotement ou affichage prématuré du formulaire.
- **Retry automatique & Manuel** : Ajout d'une relance automatique de connexion toutes les 3 secondes en cas de défaillance réseau, accompagnée d'un bouton de tentative manuelle "🔄 RÉESSAYER".

## [1.16.0] - 2026-06-14

### Nouvelles fonctionnalités & Améliorations

- **Éditeur d'Avatar Visuel (Canvas)** : Ajout d'une interface modale interactive à l'importation de l'image de l'avatar (zoom 0.5x à 4x, et recadrage/déplacement par glisser-déposer sur PC et mobile).
- **Couleur de fond personnalisée** : Option de choix d'une couleur de fond (Transparent, Blanc, Noir, Bleu Alanbix, Sombre ou Couleur personnalisée via un color picker) pour remplir les parties transparentes des images PNG à l'importation.
- **Sélecteur de format d'affichage** : Option permettant de choisir le format de rendu de l'avatar (Cercle, Carré arrondi, Carré pur) enregistré en base de données.
- **Propagation globale du masque d'avatar** : La forme de l'avatar choisie par chaque joueur est répercutée partout où son icône est affichée (Sidebar, Dashboard Leaderboard, Trophées de profil, Messagerie instantanée, Chat IA, Brackets de Tournois, Plan de salle 2D et Mode Projecteur public).
- **Optimisations de performances** : Remplacement des filtres de flou lourds (`backdrop-filter`) par un assombrissement opaque (`rgba(0, 0, 0, 0.9)`) pour économiser les ressources processeur des utilisateurs.
- **Ergonomie** : Blocage automatique de la sélection de texte durant le déplacement de l'image de l'avatar pour éviter les comportements confus.
- **Plan de salle optimisé** : Réduction légère de la taille des icônes d'avatars de la carte 2D (de 22px à 18px) pour conserver l'affichage du nom de l'équipe même lorsqu'un avatar est présent.

## [1.15.5] - 2026-06-06

### Corrections de bugs

- **Synchronisation des versions** : Alignement complet des numéros de version (v1.15.5) entre le code (package.json), le fichier système et l'affichage de l'interface.
- **Affichage des notes de mise à jour (Unraid)** : Correction du `Dockerfile` qui ne copiait pas les fichiers métadonnées, empêchant la lecture du CHANGELOG dans l'image de production unifiée.


## [1.15.4] - 2026-06-06

### Nouvelles fonctionnalités & Améliorations

- **Redimensionnement du chat (Joueurs)** : Ajout d'une barre de redimensionnement permettant d'élargir le panneau de conversation jusqu'à 70% de la largeur de l'écran. L'ajustement est sauvegardé de manière persistante.
- **Animation de l'écran de chargement** : Ajout d'une animation dynamique de "distillation" (logo incliné, bulles, effet de pulsation) sur l'écran de chargement principal.
- **Interface Admin (IA)** : Augmentation de la taille des champs de saisie pour les prompts de l'IA. La hauteur des encarts s'ajuste désormais parfaitement entre les différentes colonnes.

### Corrections de bugs

- **Arbres de tournois** : Désactivation de la sélection de texte lors du glisser-déposer à la souris pour éviter les comportements inattendus lors du déplacement sur la page.
- **Affichage des dates (TimeAgo)** : Correction du calcul du décalage horaire pour les notifications et les messages de discussion. Les dates retournées par le serveur sont maintenant correctement interprétées en UTC afin de refléter l'heure locale exacte de l'utilisateur.


## [1.15.3] - 2026-06-06

### Nouvelles fonctionnalités

- **Suivi et notifications des réponses IA / Admin pour le joueur** :
  - **Badge sur le lien de navigation** : Un compteur rouge s'affiche à côté de l'onglet « Assistant IA » dans la barre latérale pour notifier le joueur lorsqu'une réponse de l'IA (ou une intervention d'un administrateur) est reçue s'il se trouve sur une autre page.
  - **Highlight et badge Nouveau en temps réel** : Dans l'interface de l'IA, les conversations contenant des réponses non lues sont mises en évidence par une bordure verte et un badge « Nouveau ».
  - **Gestion en temps réel** : La mise à jour s'effectue instantanément via WebSocket (aucun F5 requis), et l'état lu est réinitialisé dès que le joueur sélectionne ou charge la conversation concernée.
  - **Pas de doublons** : L'envoi d'un message par l'admin n'affiche plus de double toast (la notification système se chargeant du message classique).

## [1.15.2] - 2026-06-06

### Corrections de bugs

- **Badges non lus en temps réel (Admin - Conversations IA)** :
  - **Aucun F5 nécessaire** : Les badges « Nouveau » et le compteur de l'onglet « Conversations IA » se mettent à jour en temps réel via WebSocket, sans rechargement de page.
  - **Disparition immédiate au clic** : Le badge vert et le highlight d'une conversation disparaissent instantanément quand l'administrateur clique dessus (mise à jour optimiste locale avant l'appel API).
  - **Anti-réintroduction** : `loadAdminConversations()` préserve maintenant l'état lu de la conversation active, empêchant le serveur de réintroduire le badge après un rafraîchissement de liste.
  - **Distinction user vs bot** : Le backend envoie maintenant un champ `role` dans les événements WebSocket `chat_updated` ; seuls les messages de rôle `user` incrémentent le compteur non lu pour l'administrateur (pas les réponses de l'IA).
  - **Badge dès le chargement** : Le badge de l'onglet « Conversations IA » est calculé dès le chargement de la page d'administration, sans avoir à cliquer sur l'onglet.

## [1.15.1] - 2026-06-06

### Nouvelles fonctionnalités

- **Compteur et suivi des messages non lus (Administration - Conversations IA)** :
  - **Badge sur l'onglet** : Affichage dynamique du nombre total de messages non lus par l'administrateur à côté de l'intitulé d'onglet "Conversations IA".
  - **Détails par discussion** : Indication du nombre exact de nouveaux messages non lus (ex: `2 nouveaux`) sur chaque carte de conversation de la liste latérale.
  - **Highlight dynamique** : Conservation de la bordure verte d'accentuation sur les conversations tant que l'administrateur ne les a pas lue.
  - **Marquage comme lu automatique** : Une conversation est automatiquement marquée comme lue au moment où l'administrateur clique pour l'ouvrir.

## [1.15.0] - 2026-06-06

### Nouvelles fonctionnalités

- **Modale de statistiques des joueurs (Leaderboard)** -- Clic sur un joueur dans le leaderboard (ou dans la liste des membres d'une équipe) ouvre une modale opaque affichant ses statistiques détaillées :
  - **Résumé des stats** : Points totaux accumulés, nombre de participations à des tournois et nombre de trophées remportés.
  - **Tournois & Inscriptions** : Liste des tournois auxquels le joueur participe ou est inscrit, avec badge d'état (`INSCRIT`, `EN COURS`, `TERMINE`), rang final, et répartition détaillée des points (participation, placement, score/bonus).
  - **Trophées & Distinctions** : Liste des récompenses spéciales (awards) décernées au joueur.
- **Amélioration du monitoring de l'onglet "Conversations IA" (Administration)** -- Ajout d'indicateurs d'état et d'activité des conversations pour les administrateurs :
  - **Dernière activité & Tri** : Affichage de la date et de l'heure du dernier message avec tri automatique par ordre de récurrence (récentes en premier).
  - **Aperçu du dernier message** : Affichage d'un court extrait du dernier message précédé de l'icône de l'auteur dans la liste latérale.
  - **Badge de nouveau message** : Un badge `Nouveau` et une bordure verte distincte s'affichent sur les conversations en attente de réponse (dernier message envoyé par le joueur).
  - **Détails d'exécution de l'IA (Métadonnées)** : Affichage du modèle/instance utilisé, du temps de réponse en secondes (`⏱️`) et des outils exécutés (`🛠️`) sous chaque réponse du bot.
  - **Horodatage complet** : Horodatage précis au format `JJ/MM/AAAA HH:MM:SS` pour chaque message dans la vue détaillée.

### Corrections de bugs

- **Suppression du flash du Dashboard pour les sessions expirées** -- Implémentation d'un écran de chargement translucide pendant la vérification d'authentification (`api.get('/me')`) au chargement du layout principal du dashboard. Cela empêche l'affichage transitoire du menu d'administration et du dashboard avant la redirection vers la page de connexion lorsque la session a expiré.
- **Modale de gestion du contexte opaque** -- Ajout d'un fond opaque (`var(--bg-secondary) !important`) sur la modale `.modal-content` de l'assistant IA, empêchant la discussion en arrière-plan d'apparaître par transparence et garantissant une lisibilité parfaite des options de compression.

---

## [1.13.0] - 2026-05-22

### Nouvelles fonctionnalites

- **Notifications de Prix Différées & Bouton de Diffusion** -- Les notifications ne sont plus envoyées immédiatement aux joueurs lors du calcul automatique ou de la mise à jour des prix. Un bouton dédié **📢 Diffuser les Prix aux Joueurs** a été ajouté sur la page d'administration centrale pour permettre aux organisateurs de contrôler précisément le moment de l'annonce officielle (par exemple, lors de la cérémonie de clôture de la LAN).
- **Endpoint de Notification Groupée** -- Implémentation de `POST /admin/awards/notify` pour créer toutes les notifications et diffuser les événements WebSocket en une seule fois, incluant une vérification de doublons pour éviter les renvois multiples involontaires.

---

## [1.12.0] - 2026-05-22

### Nouvelles fonctionnalites

- **Systeme de Prix Statistiques Automatiques** -- Transition complete vers un pipeline 100% stats-driven et automatise pour les prix de fin de LAN. Les 12 categories de distinctions (Premier de la LAN, Loup Solitaire, Marathonien, Bourreau, etc.) sont dorenavant calculees en temps reel d'apres les brackets de jeu.
- **Personnalisation & Templates de Prix** -- Interface d'administration entierement revue permettant de modifier en direct les titres et descriptions de chaque categorie, avec support des variables dynamiques d'interpolation (ex: `{points}`, `{wins}`). Option de restauration simple des textes par defaut.
- **Integration et Declenchement Automatique** -- Synchronisation automatique complete lors de la cloture (close) ou de la reouverture (reopen) de tournois, assurant que les notifications en temps reel (trophees remportes) sont instantanement transmises aux joueurs concernes en cas de changement de recipiendaire.

---

## [1.11.0] - 2026-05-22

### Nouvelles fonctionnalites

- **Systeme de Prix & Distinctions (Prix de fin de LAN) (AXE-43)** -- Ajout d'un systeme complet permettant aux administrateurs de decerner des prix classiques ou humoristiques a la fin de l'evenement.
- **Moteur de Suggestions Statistiques** -- Algorithme automatique analysant les brackets pour suggerer 12 distinctions differentes basees sur les performances reelles des joueurs (Meilleur joueur, Meilleure equipe, Loup solitaire, Marathonien, Passoire, Survivant du LB, L'Important c'est de participer, etc.).
- **Notifications & Profils** -- Creation de notifications temps reel de type "award" (icone 🎁) et affichage anime des trophees remportes sur la page de profil et dans l'historique des points des joueurs.
- **Purge de la base de donnees** -- Option de purge globale des prix et distinctions ajoutee dans la Zone de Danger de la page d'administration.

---

## [1.10.0] - 2026-05-22

### Nouvelles fonctionnalites

- **Barre de progression discrete & Chronometre (AXE-41)** -- Integration visuelle de la progression dans la couleur de fond des bulles du chat, avec affichage en haut a gauche du temps de reponse calcule a partir du Time to First Token (TTFT) pour une meilleure precision.
- **Persistance des statistiques par instance** -- Sauvegarde permanente des deques de durees moyennes par instance Ollama en base de donnees via la configuration systeme, avec affichage des badges de performance dans l'onglet des instances d'administration.
- **Outil d'auto-moderation IA (Anti-abus) (AXE-42)** -- Ajout de l'outil `block_user_from_ia` permettant a l'IA de bloquer de sa propre initiative les utilisateurs abusifs ou grossiers (tout en exemptant automatiquement les comptes administrateurs de cette sanction).
- **XML Fallback pour l'appel d'outils** -- Developpement d'un parser robuste d'extraction et d'execution d'outils base sur des balises XML de secours `<tool_call>`, rendant le support des outils tiers pleinement fonctionnel sur les modeles comme DeepSeek-R1 ou les petits modeles ne supportant pas Ollama tool-calling nativement.
- **Autofocus automatique** -- Focus automatique du champ de texte du chat des la fin de la generation ou lors du changement de salon de discussion.

### Ameliorations

- **Option auto-moderation** -- Toggle d'activation granularise ("Auto-moderation (Anti-abus)") integre dans les parametres IA de l'Administration pour rendre l'outil optionnel.
- **Robustesse du temps de reponse** -- Pause du chronometre de progression et soustraction automatique de la duree d'execution des outils pour ne pas fausser les statistiques de latence de l'IA.

---

## [1.9.2] - 2026-05-22

### Nouvelles fonctionnalites

- **Persistance des metadonnees IA (modele, instance, outils)** -- Les badges d'information (modele utilise, instance GPU, outils executes) restent desormais affiches de maniere permanente sur chaque message bot, meme apres rechargement de la page. Colonne `meta` JSON ajoutee en base de donnees et rendue via les endpoints API.
- **Saisie multiligne du prompt IA** -- Support de `Shift+Entree` dans le champ de saisie de l'assistant pour composer des messages sur plusieurs lignes sans envoyer.

### Ameliorations

- **Administration : refactoring de l'interface** -- Amelioration generale de la page d'administration (structure, lisibilite, organisation des sections).

---

## [1.9.1] - 2026-05-19

### Nouvelles fonctionnalites

- **Mises a jour en temps reel du dashboard Admin** -- Le tableau de bord administrateur se rafraichit automatiquement via WebSockets lors d'evenements systeme (tournois, joueurs, etc.).

### Corrections de bugs

- **Calcul du leaderboard en temps reel** -- Utilisation de `_compute_projected_standings` partage pour calculer les points en direct y compris pour les tournois FFA en cours.
- **Correction route async `update_ia_config`** -- Correction de l'import relatif de `ia_queue` et passage du handler en `async` pour supporter `asyncio.create_task`.

---

## [1.9.0] - 2026-05-19

### Nouvelles fonctionnalites

- **Decoupage RAG intelligent** -- Amelioration du chunking de la base de connaissances IA pour un meilleur contexte de reponse.
- **Chat admin en direct** -- Les administrateurs peuvent intervenir en temps reel dans les conversations IA des utilisateurs.
- **Editeur de base de connaissances** -- Interface d'edition/suppression des entrees de la Knowledge Base directement depuis l'administration.
- **Auto-titre asynchrone** -- Generation du titre de conversation IA de maniere non bloquante.

### Corrections de bugs

- **Correction BYE en brackets** -- Gestion correcte des BYE dans les tournois a elimination directe lorsque le nombre de participants n'est pas une puissance de 2.

---

## [1.8.1] - 2026-05-19

### Corrections de bugs

- **Classement championnat ex-aequo** -- Correction du tri des joueurs a egalite de points au demarrage d'un tournoi.
- **UI booleenne checkbox** -- Amelioration des checkboxes de mode booleen (V/D) dans l'interface de scoring.

---

## [1.8.0] - 2026-05-19

### Nouvelles fonctionnalites

- **Defilement automatique intelligent (Smart Scroll) (AXE-37)** : Defilement automatique du Chat IA pendant la generation, avec desactivation automatique si l'utilisateur scrolle vers le haut manuellement et reactivation lorsqu'il revient au bas du chat.
- **Indicateur d'Etat & Pensee du LLM (AXE-38)** : Rendu reactif en temps reel de la progression du modele (file d'attente, reflexion, appel d'outil, generation) avec affichage du cheminement de pensee (`<think>`) collapsible.
- **Outils de Diagnostic LAN/Reseau & Regles de Jeux (AXE-39)** : Nouveaux outils IA (`ping_host`, `traceroute_host`, `dns_lookup`, `check_server_health`, `scan_local_network`, `get_game_rules`) permettant a l'IA d'analyser le serveur et le reseau local, activables ou desactivables depuis les options IA de l'Administration.

### Corrections de bugs

- **Integrite du scoring de tournoi** : Correction d'erreurs `TypeError: '>' not supported between instances of 'NoneType' and 'int'` lors de la fermeture des tournois ou de l'avancement des manches de tournois FFA ayant des scores non saisis ou effaces (`None`).
- **Fiabilite des suites de tests unitaires** : Correction du script de test pour gerer les scores `None` au lieu de `0` lors de la simulation de scoring, rendant la suite de tests backend 100% passante.

---

## [1.7.0] - 2026-05-18

### Nouvelles fonctionnalites

- **Systeme de Versioning Automatise (AXE-30)** : Centralisation du suivi des versions sur un seul fichier `VERSION` racine et suppression des fichiers redondants pour eviter les desynchronisations.
- **Hook Git Pre-Push** : Automatisation d'un rappel push pour forcer la publication des releases et des tags correspondants sur GitHub.
- **Badge de Version en Direct** : Integration du badge dans la barre laterale du dashboard se mettant a jour via l'endpoint `/health`.

---

## [1.6.0] - 2026-05-16

### Nouvelles fonctionnalites

- **Configuration des Points de Tournoi (AXE-14)** -- Nouvelle interface d'administration pour definir les points par defaut :
  - Parametrage persistant (via `SystemConfig`) des gains pour Placement (1er, 2e, 3e), Participation (par match joue) et Bonus (par score).
  - Les formulaires de creation de tournois utilisent automatiquement ces valeurs par defaut.
- **Narrations IA Enrichies (G-25)** -- Le moteur de generation de messages de cloture est plus intelligent :
  - Remplacement des abbreviations techniques (R1, WB, LB) par des termes naturels comprehensibles.
  - Injection detaillee du detail des points (Placement, Bonus, Participation) dans le prompt pour des messages felicitant la regularite ou la performance.
  - Fix de la limite de contexte IA : le parametre `context_window` de l'administration s'applique dorenavant dynamiquement a la generation (num_predict) pour eviter que les longs messages ne soient tronques en JSON invalide.

### Corrections de bugs

- **Badge de Notifications Global** -- Fix du bug ou le compteur "1" de notification restait bloque dans le menu lateral apres avoir clique sur "Reessayer" ou supprime un message. Le statut se synchronise desormais instantanement sans necessiter un rechargement de page.
- **Securite JSON Ollama** -- Application du mode strict `format: "json"` sur les appels API de notifications pour empecher toute tentative de generation en Markdown par le modele.

---

## [1.5.0] - 2026-05-15

### Nouvelles fonctionnalites

- **Messagerie de Groupe & Inter-Equipes (AXE-12)** -- Deux nouveaux types de canaux de chat :
  - Chat d'equipe prive : clic sur le nom de sa propre equipe, salon reserve aux membres.
  - Chat inter-equipes : clic sur une equipe adverse, salon commun entre les deux equipes (trash-talk, coordination).
  - Channel keys deterministes (`team:NomEquipe`, `inter:EquipeA|EquipeB`) pour unicite garantie.
  - Sender names affiches dans les bulles de groupe.
  - Badge non-lu violet pulsant directement sur le nom de chaque equipe dans l'annuaire.
- **Gestionnaire de fichiers (AXE-13)** -- Section Fichiers utiles sur la page Informations :
  - Upload de fichiers par les admins (max 100 MB, noms sanitises, deduplication automatique).
  - Telechargement direct par les joueurs avec icones par type de fichier (.torrent, .zip, .pdf, .exe).
  - Suppression individuelle avec confirmation inline + bouton Nuke pour tout supprimer d'un coup.

### Ameliorations

- **Badge sidebar combine** -- Le compteur de messages non lus dans la sidebar cumule desormais les messages P2P + les messages de groupe via un store derive (`totalMsgUnread`).
- **WebSocket `group_message_new`** -- Nouveau type d'evenement temps reel pour les canaux de groupe, avec refresh automatique du chat ouvert et des badges.
- **Elements logistiques Plan de Salle (AXE-09)** -- Ajout d'elements de mobilier (Porte, Cuisine, Bar, WC, Rack technique, Ecran) dans l'editeur du plan de salle avec drag & drop et rotation.
- **Verrouillage de scores (AXE-15)** -- Delai de saisie 5s pour joueurs, verrouillage des matchs termines, indicateur visuel.
- **Proxy `/data`** -- Le frontend proxifie desormais `/data` vers le backend pour le telechargement de fichiers depuis le volume persistant.

---

## [1.4.0] - 2026-05-15

### Nouvelles fonctionnalites

- **Delai de saisie des scores (5s)** -- Les joueurs disposent d'un compte a rebours de 5 secondes avant la soumission effective du score.

### Securite & Integrite (AXE-15)

- **Verrouillage des scores finalises** -- Un joueur ne peut plus modifier un score de match termine. Seul un admin peut corriger un score valide.
- **Garde backend HTTP 403** -- L'endpoint `PUT /tournaments/{id}/score` rejette toute tentative de modification d'un match finalise par un non-admin.
- **Indicateur visuel** -- Les matchs verrouilles affichent un cadenas a la place du champ de saisie pour les joueurs concernes.

### IA & Outils

- **Tool `get_player_seat`** -- Nouveau tool IA pour localiser un joueur dans la salle (format T{table}_S{siege}) avec affichage des voisins de table.
- **Fuseau horaire corrige** -- Le tool `get_current_datetime` utilise desormais `Europe/Paris` pour l'heure locale LAN.
- **Fiabilite tool-calling** -- Refactoring du moteur `ia_queue.py` : detection d'outils sur un contexte minimal pour eviter les hallucinations du modele.

---

## [1.3.0] - 2026-05-15

- Page Joueurs avec badges messages non lus en temps reel
- Navigation chat directe depuis la liste joueurs
- Notifications synchronisees via store reactif partage
- Documentation README enrichie

## [1.2.0] - 2026-05-14

- Page d'informations generale (AXE-02) avec editeur Markdown admin
- Optimisation GPU (G-49) : animations CSS compositables
- Theme dynamique light/dark unifie
- Resolution noms d'equipes bracket triple couche (G-51)
- Auto-titre conversation IA inline SSE (G-50)

## [1.1.0] - 2026-05-13

- Systeme de notifications IA post-tournoi
- Widget statut IA temps reel
- Boutons Nuke admin pour purge bulk
- Blocage IA par joueur (ia_blocked)
- Spectateur bracket synchronise avec auto-cycling

## [1.0.0] - 2026-05-12

- Release initiale Alanbix
- Gestion tournois (Single/Double Elim, Round Robin, FFA)
- Plan de salle interactif
- Chat IA avec Ollama (multi-instance)
- Leaderboard global avec points distribues
- Vue spectateur projecteur
