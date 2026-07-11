# 🚀 Quick Start Guide

This guide helps you install and configure Alanbix for the first time for your event.

---

## 💾 Prerequisites
* **Docker & Docker Compose** installed on your LAN server.
* **Ollama** (optional but recommended for AI) running locally or on the network.

---

## 🛠️ Step 1: Deployment

Alanbix can be installed in three different ways depending on your production and development needs.

### Option A: From Docker Hub (Recommended for Production)
For a quick deployment without compiling the code, use the unified standalone image available on Docker Hub (`aschefr/alanbix:latest`):

```bash
docker run -d \
  -p 41481:41481 \
  -v alanbix_data:/app/data \
  --name alanbix \
  aschefr/alanbix:latest
```

* The application runs on the single port `41481` (which serves both the frontend and the backend).
* SQLite database files and uploads are stored in the persistent volume `alanbix_data`.

---

### Option B: Clone the Repository (For Development and Code Changes)
If you wish to modify the code or run the project locally with Hot Module Replacement (HMR):

1. Clone the git repository:
   ```bash
   git clone https://github.com/Aschefr/Alanbix.git
   cd Alanbix
   ```
2. **(Optional - For LAN network access)**: If you want to access the app from other devices on your local network:
   * Copy the example environment file:
     ```bash
     cp .env.example .env
     ```
   * Open `.env` and set `LAN_IP` to your server's local IP address (e.g., `LAN_IP=192.168.1.50`).
3. Launch the development containers:
   ```bash
   docker compose up -d --build
   ```
4. The application is then accessible at:
   * **Web Interface (Frontend)**: `http://localhost:41481` (or `http://<YOUR_LAN_IP>:41481` from the LAN)
   * **API Documentation (Backend)**: `http://localhost:8000/docs`

---

### Option C: On Unraid (Community Applications / XML Template)
Alanbix has an official Unraid template:

1. Open the **Docker** tab in your Unraid interface.
2. Click on **Add Container**.
3. In the **Template** dropdown, select **User Templates > Alanbix**.
4. *(If the template does not appear)*: Copy the `unraid-template.xml` file located at the root of the Git repository into the `/boot/config/plugins/dockerMan/templates-user/alanbix.xml` directory of your Unraid USB flash drive.
5. Enter the port (default `41481`) and the `appdata` path for data persistence.
6. Click **Apply** to start the container!

---

---

## 👑 Step 2: Create the Administrator Account

Alanbix automatically assigns global administration rights to the **first user created** in the application.

1. Go to `http://localhost:41481`.
2. Click on **Register** (S'inscrire).
3. Fill out the form (username and password).
4. Once logged in, you will see the **Administration** tab (🛡️) appear in your left sidebar.

![Alanbix Dashboard](../../screenshots/alanbix_dashboard.png)

---

## ⚙️ Step 3: Global Configuration

Go to **Administration > Settings** (Paramètres):

* **LAN Name**: Personalize the application header (e.g., *Retro LAN 2026*).
* **Team Scoring Mode**:
  * *Raw*: Sum of all members' points.
  * *Weighted*: Sum divided by team size (prevents penalizing smaller teams).
* **System Prompt**: Personalize the AI's personality (e.g., *"You are the official commentator for a fun LAN party"*).

---

## 🎮 Step 4: Games, Room Plan & AI

For features to be usable, the administrator must prepare the environment:

1. **Adding Games**: In **Administration > Games**, create entries for the games featured in your tournaments. Use the integrated SearXNG search to automatically download game covers directly to your server for offline-first capabilities.
2. **Room Plan**: In **Administration > Room Plan**, arrange seats, tables, and other logistical furniture via Drag & Drop. Players can then click on these seats to reserve their physical location in the room.
3. **AI Activation**: In **Administration > AI & Settings**, add your Ollama instance (e.g., `http://192.168.1.100:11434`), assign it a model, and verify its status (🟢 Connected).

---

## 🏆 Step 5: Launching the First Tournament

1. Go to **Administration > Tournaments > New Tournament**.
2. Follow the 3-step wizard:
   * **General**: Name the tournament, associate the pre-configured game.
   * **Format**: Choose whether it is solo or team-based (and define the team size).
   * **Bracket & Points**: Choose the bracket format (e.g., *Double Elimination*) and configure points for wins, participation, scores, etc.
3. The created tournament will appear with the **OPEN** status. Your players can register directly from their dashboard!

---

Next step: Consult the **[Tournament Engine](features/tournaments.md)** guide to learn how to manage and close brackets.
