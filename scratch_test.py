import sqlite3, urllib.request, json
conn = sqlite3.connect('backend/data/alanbix.db')
c = conn.cursor()
c.execute("INSERT INTO games (name) VALUES ('Test Game 123')")
game_id = c.lastrowid
c.execute("INSERT INTO tournaments (name, game_id, status) VALUES ('Test Tourney 123', ?, 'OPEN')", (game_id,))
conn.commit()
conn.close()

req = urllib.request.Request('http://localhost:8000/tournaments', method='GET')
resp = json.loads(urllib.request.urlopen(req).read())
print(json.dumps([t for t in resp if t['game_id'] == game_id], indent=2))
