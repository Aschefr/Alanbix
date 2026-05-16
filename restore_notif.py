import sqlite3
import json

conn = sqlite3.connect(r'd:\Code Projects\Alanbix\data\alanbix.db')
c = conn.cursor()

c.execute("SELECT id FROM users WHERE is_admin = 1")
admins = [row[0] for row in c.fetchall()]

c.execute("SELECT id, name FROM tournaments WHERE status = 'CLOSED' ORDER BY id DESC LIMIT 1")
row = c.fetchone()
if row:
    tid, tname = row
    for admin_id in admins:
        meta = json.dumps({"tournament_id": tid, "error": True})
        c.execute("""
            INSERT INTO notifications (user_id, type, title, content, is_read, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (admin_id, 'system', f'⚠️ Échec IA — {tname}', 'La génération de messages a été interrompue par le redémarrage du serveur. Veuillez réessayer.', 0, meta))
    conn.commit()
    print("Notification inserted.")
else:
    print("No closed tournament.")

conn.close()
