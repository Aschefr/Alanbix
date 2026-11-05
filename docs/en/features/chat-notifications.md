# 💬 Direct Messaging & Notifications

Alanbix integrates real-time communication channels and a unified notification center to streamline information exchange and animate the event.

---

## ✉️ Chat Systems (Real-Time)

Alanbix manages chat streams via persistent WebSocket connections (`/ws` handled in `websockets.py`). Messages are instantly delivered to recipients without requiring them to refresh their page.

### 1. Peer-to-Peer Private Chat (P2P)
* By clicking on a player profile from the directory, a direct messaging space opens.
* Messages are stored in the SQLite `private_messages` table.
* The system automatically generates red notification badges with an unread message count next to the sender's name in the directory and on the global messaging tab in the sidebar.

![Player directory](../../../screenshots/en/players.png)

![Private conversation](../../../screenshots/en/messages.png)

* **The Messages tab**: With an unread message, it opens the conversation (private or team) holding the newest one. On a phone, a second tap switches between the conversation and the contact list.

### 2. Deterministic Team Group Channels (G-53)
For team tactics and LAN community needs, Alanbix integrates a group chat system with channel keys calculated deterministically server-side:
* **Private Team Chat (🛡️)**: Reserved exclusively for players sharing the same `User.team_name`.
  * *Channel Key*: `team:[TeamName]` (e.g., `team:Alpha Wolves`).
  * The interface access buttons feature a distinctive purple pulsing animation.
* **Inter-Team Chat (⚔️)**: Allows two different teams to challenge each other or chat.
  * *Channel Key*: `inter:[TeamNameA]|[TeamNameB]`. The names are systematically sorted alphabetically to guarantee that the channel key is identical regardless of who initiates the chat.
  * *Security Control*: Only members of the two concerned teams (or an administrator) can read or post in this channel. The backend rejects any other attempt.

### 3. Shared Rich Chat Features (P2P & Groups)
Both direct and group chats enjoy the full modern feature set of the public chat:
* **Live Emoji Reactions**: Quick hover bar (`👍`, `🔥`, `🏆`, `➕` with full categorized picker) and interactive reaction counter pills.
* **Replies & Contextual Quotes**: Reply button (`↩`) with instant jump and highlight animation to original message.
* **Image & Meme Attachments**: Send images (PNG, JPG, WebP, GIF up to 8MB) via drag-and-drop, clipboard paste (`Ctrl+V`), or attachment paperclip button, with preview thumbnail and full-screen lightbox.
* **Automatic Link Previews (OpenGraph)**: Rich cards featuring site title, description, and thumbnail for posted URLs.
* **Real-time Typing Indicators**: Live visibility of peers currently typing via WebSockets.
* **Sound Alerts & Profanity Filter**: Gentle Web Audio chime on direct `@username` mention (with header mute toggle `🔊`/`🔇`) and client-side courtesy shield (`🛡️`/`👁️`) masking offensive words (`f**k`).
* **Privacy & AI Exclusion**: The `@Alanbix` bot is strictly confined to the public chat and never participates in private or team chats.

### 4. Public Room Chat & AI Mascot (Dashboard)
The main Dashboard includes a public chat open to all players and organisers of the LAN:
* **Room & Map Interaction**: When a seated player sends a message, their seat lights up on the interactive map and a chat bubble rises towards the chat panel.
* **Live typing indicator**: Shows who is typing, including `@Alanbix` preparing an answer, with rotating humorous lines; it expires after 5-6 seconds of inactivity.
* **Reactions**: Hover bar, the 4 recently used emojis (kept in `localStorage`), a full picker with search and tabs (Recent, All, Gaming & LAN, Gamer Tags such as `GG`, `EZ`, `WP`, Smileys, Gestures, Symbols), and clickable counters updated live.
* **Replies & Quotes**: A `↩️ Reply` button opens a preview bar above the input (cancel with `✕` or `Esc`); the sent message carries a clickable quote that scrolls back to the original.
* **Pinned Message**: A discreet banner under the chat header for important announcements, controlled by organisers; a click scrolls to the original message.
* **Mention Sounds**: A soft chime generated with the Web Audio API (100% offline), only when a player is mentioned directly (`@MyName`), with a toggle in the chat header.
* **Media & Moderation**: Images and GIFs (up to 8 MB), OpenGraph link previews, an unread line with a quick return button, and moderation settings (slowmode, banned words, anti-flood).

### `@Alanbix` in the public chat
Mention `@Alanbix`, or reply (`↩`) to one of its messages, and the AI assistant joins the conversation with the personality set by the administrator. Its answer is shown as a reply to the player's message.
* **It follows the conversation**: it reads the last 20 messages (last 30 minutes) with who speaks and whom each message replies to, plus the older messages the question replies to. Its own answers are marked so it does not repeat itself.
* **It knows the player asking**: team, seat and upcoming matches, even with a small model without tools ("which match do I play?").
* **It looks up live data**: tournaments, matches, brackets, rankings, teams, seats, games and rules, files and event info, with read-only tools. The tool calling mode of the AI settings applies (off = no tools). The knowledge base is used too.
* **Nothing private, no action**: as the whole room reads the answer, it does not read a player's notifications, alert an administrator, send notifications or announcements, or block anyone. For that, it points to the private AI Assistant.
* **Never silent**: when it does not answer, the player who called it sees why, in a line under the messages that only they see: it was just called (with the seconds to wait), its answers are turned off by the organizers, or the AI is unavailable.
* **Formatting**: `**bold**`, `*italic*`, `` `code` `` and lines starting with `*` or `-` (shown as bullets) are formatted, in Alanbix's answers as in players' messages. No HTML is ever interpreted.

---

## 🔔 Notification Center (Real-Time)

The **Notifications** page of the menu (or the bell on a phone) opens the notification center (SQLite `notifications` table).

![Notification Center](../../../screenshots/en/notifications.png)

### Notification Types
1. **Match ready (`match_ready`)**: Your opponent is known and the match can start. This text shows in each player's language, like the AI failure alert for admins; the other types stay in the language they were written in.
2. **Announcements and admin messages (`admin_message`)**: Sent when an organiser publishes a general announcement or replies by hand in a conversation.
3. **Tournament closing (`tournament_closed`)**: A message written by the assistant when a tournament closes (see below).
4. **Awards (`award`)**: Sent when an administrator publishes the awards.

Each notification can be archived (**Archive** tab), and **Mark all as read** or **Archive all** act on the whole list.

### Match Summaries by AI
Upon closing a tournament, for each participant, the server adds an AI generation task to the queue.
* **The Concept**: The AI writes a personalized, teasing, or encouraging summary of the player's performance during the tournament (e.g., *"You won your first 3 matches easily before stumbling in the semi-finals against PixelHunter... Keep pushing!"*).
* **System Notification Prompt**: Configurable by the admin.
* **Resilience**: If the Ollama instance crashes or returns a timeout during message generation, the notification system displays an error alert on the admin dashboard with a **"Retry Generation"** button to re-submit the task to the AI queue without blocking the rest of the application.
