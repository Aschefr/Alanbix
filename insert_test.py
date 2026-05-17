import sqlite3
import json

conn = sqlite3.connect('backend/data/alanbix.db')
c = conn.cursor()
c.execute("INSERT INTO games (name) VALUES (?)", ("Test Game Quake",))
game_id = c.lastrowid
c.execute("INSERT INTO tournaments (name, game_id, status) VALUES (?, ?, ?)", ("Test Tourney Quake", game_id, "OPEN"))
conn.commit()
conn.close()
print("Inserted Game ID:", game_id)
