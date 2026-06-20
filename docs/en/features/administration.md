# 🛡️ System Administration & Controls

The administration panel of Alanbix (accessible only to users with `is_admin = true` in the database) groups moderation tools, game management, and application maintenance commands.

---

## 👥 Player Account Management

Accessible via the **Administration > Players** tab.

### Individual Actions
* **Manual Creation**: The administrator can register a player directly via the form by setting their username, initial password, and team.
* **Editing & Resetting**: Ability to modify the username, reset a participant's password (in case of forgetfulness), edit their global team name, or grant them administrator privileges.
* **AI Moderation**: The administrator can revoke a player's access to the AI assistant if they abuse it (which hides the AI chat from their interface).

![Player Management](../../../screenshots/alanbix_administration_joueurs.png)

### Generating a Test Pool (G-46)
To validate the correct behavior of tournament brackets or messaging without having to create 20 accounts manually:
* **The Button**: Click the **"Generate 20 test players"** button (`POST /admin/users/generate-test-pool`).
* **Result**: Instantly creates 20 dummy player accounts with gaming usernames (e.g., `FragMaster2000`, `CyberNinja`, etc.) distributed evenly across 4 predefined teams (*Alpha Wolves*, *Neon Vipers*, *Shadow Foxes*, *Iron Bears*) and assigns them random points history to populate the leaderboards. This operation is idempotent: it does not overwrite existing custom usernames.

---

## 🎮 Game Library (SearXNG Proxy)

To associate an image and rules with tournaments, administrators manage a local game catalog.
* **Creating a Game**: Go to **Administration > Games > New Game**.
* **Automatic Cover Search**: To avoid having to download and host the game cover image yourself, enter the game's name and click the search magnifying glass button. The server queries a SearXNG engine (local proxy) in the background to retrieve the official cover and saves it locally in `/app/data/game_images/` (persistent volume) to ensure offline-first capability for the LAN.
* **Manual Upload**: The administration panel also allows uploading a cover image directly from the administrator's computer.

![Game Library Management](../../../screenshots/alanbix_administration_jeux.png)

---

## 🎛️ System Settings & Inline Editing (G-24)

* **No Disruptive Modals**: In accordance with Alanbix's ergonomics charter, settings editing panels (such as tournament configuration or system information editing) display as inline collapsible accordion panels directly on the sheet concerned, rather than in a modal window that would block the screen. Only one element can be edited at a time (singleton `inlineEditId`).
* **LAN Renaming**: The administrator can modify the name of the event. The change is saved via `PUT /admin/config/event_name` and updates in real-time on all participants' dashboards via WebSockets.

![Administration Settings](../../../screenshots/alanbix_administration_param%C3%A8tres.png)

---

## ☢️ Self-Destruction Controls (NUKE Buttons) (G-08)

To facilitate database cleaning between two events or after intensive testing phases, the administration settings tab offers massive purge buttons (called **NUKE Buttons**):

* **Nuke Tournaments**: Deletes all tournaments, brackets, match history, and associated teams.
* **Nuke Players**: Deletes all player accounts (except the currently connected administrator).
* **Nuke Games**: Empties the game library and deletes associated cover image files from disk.
* **Nuke Files**: Deletes all physical files uploaded by the file manager in bulk.
* **Nuke Notifications & Messages**: Erases the entire history of private chats, team channels, and generated notifications.

### Security Ergonomics (No window.confirm)
To avoid accidental deletions while keeping a clean UI:
1. No delete or purge button uses the default browser system dialog box (`window.confirm`).
2. Instead, the button shifts to a local `delete_pending` state.
3. The button text dynamically changes to **"Are you sure?"** along with a color shift to bright red and starts a short security countdown.
4. The administrator must click a second time to confirm the final purge action.

---

## 📚 AI Knowledge Base (RAG)

To feed the memory of the local AI assistant (RAG):
* **Document Input Area**: A large text field (TextArea) is present under **Administration > AI Assistant > Knowledge Base**.
* **"Vectorize & Add" Button**: Splits the entered text, sends it to the active Ollama instance to extract semantic vectors (embeddings), and stores them in the `rag_documents` table so they are immediately usable in player chats.
* **Document Management Buttons**: Allows listing and individually deleting indexed knowledge blocks.
