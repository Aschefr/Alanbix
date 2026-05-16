import sqlite3
import urllib.request

conn = sqlite3.connect(r'd:\Code Projects\Alanbix\data\alanbix.db')
c = conn.cursor()
c.execute("SELECT id FROM tournaments WHERE status = 'CLOSED' ORDER BY id DESC LIMIT 1")
row = c.fetchone()
conn.close()

if row:
    tid = row[0]
    print(f"Retrying tournament {tid}")
    req = urllib.request.Request(f'http://localhost:8080/api/tournaments/{tid}/retry-notifications', method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            print(response.read().decode())
    except Exception as e:
        print(e)
else:
    print("No closed tournament found")
