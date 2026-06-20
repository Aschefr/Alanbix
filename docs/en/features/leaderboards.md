# 📊 Leaderboards, Statistics & Awards

Alanbix offers a complete system to track individual and team performances throughout the LAN. Leaderboards are calculated both persistently (in the database) and predictively (real-time frontend standings).

---

## 🏆 Global Individual Leaderboard

Accessible from the main tab of the Dashboard. It lists players sorted in descending order of their accumulated points in the `users` table.

### Progression Indicators (↑↓ NEW)
To make the leaderboard dynamic, the frontend memorizes the last state of the leaderboard in the `previousLeaderboard` variable (temporary persistence in local memory).
Upon each data refresh (via API or WebSocket):
* If a player goes up $N$ places: A green **↑N** badge appears next to their name.
* If a player goes down $N$ places: A red **↓N** badge appears.
* If a player was not present in the Top 10 in the previous snapshot and makes an entry: An orange **NEW** badge is displayed.
* If their position is unchanged: No badge is displayed.

---

## 👥 Team Leaderboard

This ranking groups players by the value of their `User.team_name` column (their global team declared on their profile). Team rows are colored in purple (`var(--primary-purple)`) to distinguish them from individual rankings.

### The 2 Score Calculation Modes
The administrator can choose the calculation mode from the **Administration > Settings** tab (SQLite configuration key `team_scoring_mode`):

1. **Raw Mode (`raw`)**:
   $$\text{Team Score} = \sum \text{Points of all members}$$
   *Ideal if all teams have the same number of players.*
2. **Weighted Mode (`weighted`)**:
   $$\text{Team Score} = \frac{\sum \text{Points of all members}}{\text{Number of team members}}$$
   *Recommended if team sizes are unbalanced. This prevents an 8-player team from systematically crushing a 3-player team.*

### Expandable View (Members Details)
Clicking a team row in the standings instantly expands a panel listing all members of that team, sorted by individual points, thus showing the exact contribution of each member to the global score.

---

## 🗂️ Player Sheet, Profile & Custom Avatars
Clicking a player's name anywhere in the application (leaderboards, directory, tournament tree) opens a complete profile modal (opaque background `var(--bg-secondary)`) displaying:
1. **Key Statistics**: Total score, number of tournaments played, and awards won.
2. **Match History**: The complete list of tournaments the player participated in. For each tournament, a colored badge indicates the status (**REGISTERED**, **RUNNING**, **CLOSED**), their final rank, and the detailed calculation of points obtained (e.g., +10 win, +1 participation, +1.5 goals).
3. **Trophy Showcase**: Automatic awards granted to the player.

### 🎨 Integrated Avatar Editor
From their Profile page, players can upload their own avatar. A mini-visual editor (Canvas) opens on image import to allow:
* **Zoom In / Out**: Adjust the image size (0.5x to 4x) using a slider.
* **Crop / Drag**: Reposition the image to the pixel using the mouse or finger (on smartphones).
* **Background Color (transparency)**: Fill the background of transparent PNG images with a solid color (Transparent, White, Black, Alanbix Blue, Dark, or custom color).
* **Shape Choice**: Configure the shape of the avatar rendering mask:
  * **Circle** (default)
  * **Rounded** (square with softened corners)
  * **Square** (pure square without rounding)
* **Global Propagation**: The shape chosen by the user is stored in the database and applied dynamically across the entire application interface (Sidebar, Leaderboard, Chat boxes, Tournament Brackets, 2D Room Plan, Projector view, and Admin Panel).

![Player Profile](../../../screenshots/alanbix_profile_joueur.png)

---

## 🎁 Automatic Awards System

At each tournament closing, the server runs a statistical analysis pipeline on the SQLite database to automatically assign or reassign 12 specific trophies (`awards` table).

### The 12 Managed Trophies
1. **First of the LAN**: Player occupying the 1st place in the general classification.
2. **First Team of the LAN**: Team occupying the 1st place in the team standings.
3. **The Executioner (Le Bourreau)**: Player who has inflicted the highest number of defeats (lost bracket rounds) on other players.
4. **Coop King (Le Roi du Coop)**: Player with the most wins in tournaments played in Team mode.
5. **Lone Wolf (Loup Solitaire)**: Player with the most wins in tournaments played in Solo (1v1) mode.
6. **The Marathoner (Le Marathonien)**: Player who has played the highest total number of matches, across all tournaments.
7. **Trigger Happy (Gâchette Facile)**: Player with the highest cumulative score (goals/points scored in matches).
8. **The Sieve (La Passoire)**: Player with the lowest cumulative score among the matches played.
9. **BYE's Favorite (Chouchou des BYE)**: Player who has benefited from the highest number of BYEs (slots in the bracket that moved them forward without playing).
10. **The Swiss (Le Suisse)**: Player with the highest number of draws.
11. **Losers Bracket Survivor**: Player who has played the most matches in the Losers Bracket.
12. **The Important Thing is to Participate**: Player with the fewest wins among those who have played at least 2 tournament matches.

### Notifications and Personalization
* **Real-Time Notification**: When a trophy changes hands after a tournament closes, the server instantly pushes a WebSocket notification (gift icon 🎁) to the player who just won the award.
* **Admin Personalization**: The titles and descriptions of the awards can be edited in the administration interface. The descriptions support dynamic variables interpolated by the server during display (e.g., `{points}`, `{wins}`, `{matches_played}`).

---

## 📊 Live Standings

When a tournament is in **RUNNING** status (active play):
* The system dynamically calculates on the frontend a provisional ranking based on the current state of the bracket matches (number of wins accumulated $\times$ points per win + scores scored $\times$ goal multiplier).
* This ranking displays as a mini-leaderboard directly under the bracket with a flashing **LIVE** badge.
* *Integrity Security*: This calculation is purely visual and does not alter the `points` column in the SQL database until the administrator officially closes the tournament.
