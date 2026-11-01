# 🛡️ System Administration & Controls

The administration panel of Alanbix (accessible only to users with `is_admin = true` in the database) groups moderation tools, game management, and application maintenance commands.

---

## 🧭 Guided server setup

The first account created on a new server (the admin) lands on **Server setup** (`/dashboard/setup`) instead of the player welcome. Eight steps, each of which can be skipped:

1. **The event**: LAN name and default language.
2. **The network**: LAN Wi-Fi names (recognised by the mobile app) and the address to give the players (warning when it is a `localhost` address).
3. **The info page**: a pre-filled template (schedule, Wi-Fi, food, general rules) to complete in the Markdown editor.
4. **Games and tournaments**: SearXNG check (with help to install it), adding games with their cover, the four formats explained with an example of rules, the points scale explained, and a first tournament created on the spot.
5. **The Alanbix assistant** (optional): no assistant, a local model (Ollama) or an online service with an API key; connection test, model choice and context size.
6. **The room map** (optional): table generator (number of tables, seats per table, tables per row) with a preview.
7. **Invite the players**: address, QR code and a printable poster.
8. **Summary**: "Finish" or "I'm playing too" (continues with the player welcome).

Progress is saved on the server (`admin_setup`). The administration shows a banner until the setup is finished or hidden, and **Settings › General › Guided setup** runs it again. After a full reset, it comes back.

---

## 🎚️ Control Room (default tab)

The Control Room gathers what needs the organiser's attention during the LAN:
* **Help calls**: escalations raised by the AI assistant. "View" opens the original conversation (or the player's latest one); otherwise "Message player" opens their private messages. "Resolved" and "Ignore" close the request.
* **Scores to enter**: current-round scores, entered in place; "View" opens the tournament.
* **Quick moderation**: search a player, then the "⋯" button: mute chat (15 min, 30 min, 1 h, 24 h) or unmute, block the AI, message the player, or open their full profile in Player Management.
* **Running tournaments**: progress of each tournament.

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

* **Purge the public chat**: permanently deletes every public chat message and its images, and removes the pinned message.
* **Tournaments**: deletes all tournaments, brackets, scores and tournament teams, and resets every player's points to zero.
* **Players**: deletes every non-admin account with its messages, AI conversations, notifications, devices and uploaded images; their username is removed from the standings of closed tournaments.
* **Games**: deletes every game (and therefore every tournament), their uploaded covers and thumbnails, and the knowledge base entries written for a game.
* **Images**: deletes every uploaded image (AI assistant, private and team messages, public chat) and removes their references from the messages.
* **Notifications**: deletes every player's notifications.
* **Awards**: deletes awarded prizes and customised texts, then recomputes the default awards.
* **Room map**: deletes every table, seat and element of the map, and frees every player's seat.
* **Full reset**: empties the whole server like a new installation (all data, all uploaded files, settings and customised translations). Admin accounts can be kept (username, password, avatar). Typing `RESET` confirms it; other connected people are reloaded automatically.

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

---

## 🩺 Server Memory Diagnostics
To watch a long-running server (a Raspberry Pi for example), the API exposes `GET /admin/diagnostics/memory`, restricted to administrators (same session as the app, same port).

- **Default response**: process memory (`rss_mb`), WebSocket connections, online players, AI queue, caches and async tasks. A counter that keeps climbing and never comes back down points to a leak.
- **`?top=30`**: lists the most numerous Python object types; compare two calls a while apart to see what accumulates.
- **`?trace=start`** then **`?trace=diff`**: records allocations, then shows the code lines that hold the most memory. **`?trace=stop`** stops recording (it slows the server down: use it for an analysis only).

> WebSocket connections no longer use per-message compression: each connection kept a ~37 KB context that was never freed when the network dropped abruptly (phone going to sleep). See changelog 1.35.2.
