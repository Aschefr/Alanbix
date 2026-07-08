# 🗺️ Interactive Room Plan

Alanbix's interactive room plan graphically represents the physical layout of the LAN, manages seat assignments, and makes it easy to locate participants.

---

## 🛠️ The Room Editor (Administrator View)

Accessible from **Administration > Room Plan**. This editor allows designing the physical layout of the event using an interactive 2D canvas.

### Available Elements (Sidebar Palette)
You can Drag & Drop the following elements onto the canvas:
* **Seat**: The primary element on which a player can sit.
* **Table**: Furniture of different sizes to structure rows.
* **Structural Elements**: Walls, Doors, Technical Racks, Projection Screens.
* **Amenities**: Kitchen corner, Food bar, Restrooms (WC).

![Room Editor](../../../screenshots/alanbix_plan_salle_editeur.png)

### Actions on Canvas Elements
* **Selection and Movement**: Click and hold an element to reposition it.
* **Coordinated Rotation**: Clicking the rotation handle of a table and rotating it automatically moves and aligns all associated seats in a circular arc around the table's center.
* **Delete Confirmation (Table)**: Deleting a table displays a visual confirmation overlay (`✓` / `✕`) positioned at the top-right above the table to prevent accidental clicks, and automatically cascades deletion to all associated seats.
* **Direct Seat Addition**: A green `+` button (ghost seat) appears at the next vacant physical grid slot of a table. Clicking it generates a seat with a unique sequential ID (e.g. `T5_S9` instead of conflicting IDs). The button automatically shifts or disappears depending on table resizing and its maximum capacity.
* **Tight Auto-Recentering**: The **Recenter** button (as well as the initial page load) dynamically calculates the bounding box of all elements (tables, seats, decorations) to adjust zoom and center the room plan with an optimized `15px` padding.
* **Save**: Changes automatically sync in the background with the SQLite `room_items` table.

---

## 🪑 Seat Assignment

The system manages the association between user accounts and seat IDs placed on the map.

### Self-Service Choice (Player)
* From the public Room Plan view, a logged-in player can click a free seat to reserve it.
* Their username and avatar immediately appear on the plan for all other users thanks to WebSocket synchronization.
* If the player changes their mind, they can click their own seat to "Free the seat".

![Room Plan Zoom](../../../screenshots/alanbix_plan_salle_zoom.png)

### Administration and Manual Assignment
* The administrator can click any seat and use a dropdown containing the list of registered players to manually assign a participant to a seat.
* **"Free All" Button (Bulk Unassign)**: Located in the header of the admin editor. This button sends a `POST /room/admin-unassign-all` request to the backend to instantly unassign all players in the room in one go (handy when resetting the event).

---

## 🖱️ Advanced Navigation: Cursor-Centered Zoom

To deliver a fluid experience, the room plan features a 2D manipulation engine (Pan & Zoom) written in Vanilla JS without any heavy external dependencies.

* **Centered Zoom**: Using the mouse wheel zooms directly toward the physical position of the mouse pointer (and not toward the top-left corner of the container).
* **Pan (Movement)**: Hold down the left mouse button (or drag with a finger on tablets/mobiles) to pan the map.
* **Drag-Threshold Security Filter**: The system applies a minimum pixel threshold before validating a drag movement. This prevents accidentally moving the map when a player simply wants to click their seat.

---

## 🔗 Synergy with Tournament Brackets

A unique feature of Alanbix is the cross-referencing of physical location data and the status of tournament matches:
* In the tree of an active tournament, next to each player's username in a match, a small badge represents their seat number (e.g., **#B12**).
* **Location Click**: Clicking this seat badge teleports the user directly to the Room Plan view, automatically centers the camera on that player's workstation, and applies a pulsing animation to highlight it.
