"""Fills an empty Alanbix server with invented data for the documentation screenshots, through its API.
Players, teams, games and the event are all made up. See run.py."""
import io
import json
import math
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from PIL import Image, ImageDraw, ImageFont

PASSWORD = "demo-only-password"  # Throwaway accounts on a throwaway server
PLAYERS = {
    "Alpha Wolves": ["PixelHunter", "BlazeRunner", "RocketQueen", "DragonByte", "Zephyr"],
    "Neon Vipers": ["LaserCat", "NightHawk", "GlitchMaster", "VoltStrike", "Orbit"],
    "Shadow Foxes": ["ShadowNinja", "CyberWolf", "ArcticFox", "TurboGamer", "Sable"],
    "Iron Bears": ["CosmicDust", "IcePhoenix", "StormBringer", "QuantumLeap", "Basalt"],
}


class Api:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.tokens = {}

    def login(self, name):
        if name not in self.tokens:
            data = urllib.parse.urlencode({"username": name, "password": PASSWORD}).encode()
            req = urllib.request.Request(self.base + "/token", data=data, headers={"Accept": "application/json"})
            self.tokens[name] = json.load(urllib.request.urlopen(req))["access_token"]
        return self.tokens[name]

    def call(self, method, path, body=None, as_user="Admin", file=None):
        headers = {"Accept": "application/json"}
        if as_user:
            headers["Authorization"] = "Bearer " + self.login(as_user)
        data = None
        if file:
            boundary = uuid.uuid4().hex
            filename, content = file
            mime = "image/png" if filename.endswith(".png") else "application/octet-stream"
            data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                    f"Content-Type: {mime}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            raw = urllib.request.urlopen(req, timeout=120).read()
        except urllib.error.HTTPError as e:
            raise SystemExit(f"{method} {path} -> {e.code}: {e.read()[:300]!r}")
        return json.loads(raw) if raw else None


def font(size):
    for path in ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def cover(title, top, bottom, accent, rng):
    """An invented game cover: gradient and abstract shapes."""
    w, h = 900, 1200
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        px.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(14):
        x, y, r = rng.randint(0, w), rng.randint(0, h), rng.randint(40, 260)
        d.ellipse([x - r, y - r, x + r, y + r], outline=accent + (rng.randint(50, 130),), width=rng.randint(2, 10))
    for i in range(7):
        y = 760 + i * 44
        d.line([(0, y + i * 26), (w, y - 120 + i * 12)], fill=accent + (90,), width=3)
    img = Image.alpha_composite(img.convert("RGBA"), layer)
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


def avatar(name, rng):
    hue = rng.random()
    a, b = [tuple(int(255 * (0.5 + 0.5 * math.sin(6.283 * (hue + o + k / 3)))) for k in range(3)) for o in (0, 0.15)]
    size = 256
    img = Image.new("RGB", (size, size), a)
    d = ImageDraw.Draw(img)
    for i in range(6):
        x, y, r = rng.randint(0, size), rng.randint(0, size), rng.randint(30, 90)
        d.ellipse([x - r, y - r, x + r, y + r], fill=b if i % 2 else tuple(min(255, c + 45) for c in a))
    d.text((size / 2, size / 2), name[0], font=font(120), fill=(255, 255, 255), anchor="mm")
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def room_layout():
    """Three tables of 8 seats plus the room elements, using the editor's geometry."""
    tables, seats = [], []
    for t, x in enumerate((80, 440, 800), start=1):
        y = 120
        tables.append({"id": f"T{t}", "label": f"Table {t}", "x": x, "y": y, "w": 260, "h": 80, "rotation": 0, "auto_seats": True})
        for i in range(8):
            row, col = divmod(i, 4)
            seats.append({"id": f"T{t}_S{i + 1}", "x": x + 15 + col * 60, "y": y - 65 if row == 0 else y + 95, "rotation": 0})
    furniture = [
        {"id": "F1", "type": "door", "icon": "door", "label": "Door", "x": 60, "y": 340, "w": 80, "h": 40, "rotation": 0},
        {"id": "F2", "type": "bar", "icon": "beer", "label": "Bar", "x": 200, "y": 330, "w": 200, "h": 60, "rotation": 0},
        {"id": "F3", "type": "wc", "icon": "restroom", "label": "WC", "x": 460, "y": 320, "w": 80, "h": 80, "rotation": 0},
        {"id": "F4", "type": "screen", "icon": "monitor", "label": "Screen", "x": 500, "y": 0, "w": 160, "h": 40, "rotation": 0},
        {"id": "F5", "type": "wifi", "icon": "wifi", "label": "Wi-Fi", "x": 600, "y": 330, "w": 60, "h": 60, "rotation": 0},
        {"id": "F6", "type": "rack", "icon": "server", "label": "Rack", "x": 720, "y": 320, "w": 60, "h": 80, "rotation": 0},
        {"id": "F7", "type": "kitchen", "icon": "utensils", "label": "Kitchen", "x": 860, "y": 310, "w": 160, "h": 100, "rotation": 0},
    ]
    return {"tables": tables, "seats": seats, "furniture": furniture}


def score_matches(api, tid, count, rng, section=None, draws=False, favourite=None):
    """Scores `count` playable matches of a bracket. Returns how many were scored."""
    done = 0
    while done < count:
        t = api.call("GET", f"/tournaments/{tid}")
        ready = [m for m in t["bracket"]
                 if all(p != 0 for p in m["p"]) and not (m.get("score") and all(s is not None for s in m["score"]))
                 and (section is None or m["id"]["s"] == section)]
        if not ready:
            break
        m = sorted(ready, key=lambda x: (x["id"]["s"], x["id"]["r"], x["id"]["m"]))[0]
        n = len(m["p"])
        if n == 2:
            a = rng.randint(0, 4) if draws else rng.randint(0, 3)
            b = rng.randint(0, 4) if draws else 4 + rng.randint(0, 2)
            score = [a, b] if rng.random() < 0.5 else [b, a]
            if favourite in m["p"]:
                score = sorted(score, reverse=m["p"][0] == favourite)
        else:
            score = rng.sample(range(1, n * 5), n)
            if favourite in m["p"]:
                i = m["p"].index(favourite)
                best = score.index(max(score))
                score[i], score[best] = score[best], score[i]
        api.call("PUT", f"/tournaments/{tid}/score", {"match_s": m["id"]["s"], "match_r": m["id"]["r"], "match_m": m["id"]["m"], "score": score})
        done += 1
    return done


def wait_for_summaries(api, player):
    """Closing a tournament queues the AI summaries: wait until they are written."""
    for _ in range(30):
        notes = api.call("GET", "/notifications", as_user=player)
        items = notes if isinstance(notes, list) else notes.get("items") or notes.get("notifications") or []
        if any(n.get("type") not in ("match_ready", None) for n in items):
            return
        time.sleep(1)
    print("AI summaries not found, carrying on")


def main(base, lang):
    fr = lang == "fr"
    rng = random.Random(42)
    api = Api(base)
    req = urllib.request.Request(base.rstrip("/") + "/register", data=json.dumps({"username": "Admin", "password": PASSWORD}).encode(),
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    urllib.request.urlopen(req)

    # Event settings: the guided setup is marked done so that no banner covers the pages
    api.call("PUT", "/admin/config/admin_setup", {"value": {"status": "done", "current": "recap", "steps": {}}})
    api.call("PUT", "/admin/config/event_name", {"value": "Alambic LAN 2026"})
    api.call("PUT", "/admin/config/lan_default_language", {"value": lang})
    api.call("PUT", "/admin/config/team_scoring_mode", {"value": "weighted"})
    api.call("POST", "/ia/config", {
        "ollama_instances": [{"url": "http://ollama.lan:11434", "label": "RTX 3090", "model": "gemma4:e4b", "enabled": True, "priority": 0, "num_ctx": 8192}],
        "temperature": 0.2,
    })

    names = [n for team in PLAYERS.values() for n in team]
    for team, members in PLAYERS.items():
        for name in members:
            api.call("POST", "/admin/users/create", {"username": name, "password": PASSWORD, "team_name": team})
    users = {u["username"]: u["id"] for u in api.call("GET", "/room/users", as_user="Admin")}
    for name in names[:-2]:
        api.call("POST", "/me/avatar", as_user=name, file=(f"{name}.png", avatar(name, rng)))

    # Room plan and seats (two seats stay free)
    layout = room_layout()
    api.call("POST", "/room/layout", layout)
    seats = [s["id"] for s in layout["seats"]]
    for name, seat in zip(["Admin"] + names[:-1], seats):
        api.call("POST", "/room/admin-assign-seat", {"user_id": users[name], "seat_id": seat})

    # Invented games with generated covers
    games = {}
    palette = {
        "Iron Arena": ((70, 20, 30), (20, 15, 35), (255, 120, 60)),
        "Neon Drift": ((30, 10, 90), (5, 60, 110), (60, 240, 230)),
        "Goal Rush": ((10, 90, 60), (10, 30, 60), (180, 255, 90)),
        "Kart Frenzy": ((180, 60, 20), (90, 20, 90), (255, 220, 60)),
        "Castle Siege": ((50, 50, 80), (20, 20, 30), (220, 190, 120)),
        "Rocket Duo": ((20, 40, 130), (10, 10, 40), (255, 90, 160)),
    }
    rules = {
        "Iron Arena": ("Duel en 1 contre 1, première à 5 manches. Carte tirée au sort.", "1v1 duel, first to 5 rounds. Random map."),
        "Neon Drift": ("Course à 4 joueurs, 3 tours. Points selon l'arrivée.", "4-player race, 3 laps. Points by finishing position."),
        "Goal Rush": ("Matchs de 5 minutes. Le match nul est possible.", "5-minute matches. Draws are allowed."),
        "Kart Frenzy": ("Grand Prix en 4 courses, objets activés.", "4-race Grand Prix, items on."),
        "Castle Siege": ("Une partie par tour, carte Standard. Le vainqueur note le score.", "One game per round, Standard map. The winner enters the score."),
        "Rocket Duo": ("Équipes de 2, 3 buts pour gagner.", "Teams of 2, first to 3 goals."),
    }
    for name, (top, bottom, accent) in palette.items():
        img = api.call("POST", "/tournaments/games/upload-image", file=(f"{name}.png", cover(name, top, bottom, accent, rng)))
        games[name] = api.call("POST", "/tournaments/games", {"name": name, "image_url": img.get("url") or img.get("image_url"),
                                                               "rules": rules[name][0 if fr else 1]})["id"]

    points = {"pts_winner": 10, "pts_second": 6, "pts_third": 4, "pts_participation": 1, "pts_per_match": 0, "pts_per_goal": 0}

    def tournament(name, game, roster, **config):
        t = api.call("POST", "/tournaments", {"name": name, "game_id": games[game], "config": {**points, **config}})
        for player in roster:
            api.call("POST", f"/tournaments/{t['id']}/join", as_user=player)
        return t["id"]

    # A finished tournament: points, awards and notifications come from a real closing
    closed = tournament("Castle Siege Open", "Castle Siege", names[:8], bracket_type="single_elim")
    api.call("POST", f"/tournaments/{closed}/start", {})
    score_matches(api, closed, 99, rng, favourite=users["PixelHunter"])
    api.call("POST", f"/tournaments/{closed}/close", {})

    # Running tournaments, one per format
    de = tournament("Iron Arena Showdown", "Iron Arena", ["PixelHunter", "LaserCat", "ShadowNinja", "CosmicDust", "BlazeRunner", "NightHawk", "CyberWolf", "IcePhoenix"], bracket_type="double_elim")
    api.call("POST", f"/tournaments/{de}/start", {})
    score_matches(api, de, 6, rng, section=1, favourite=users["PixelHunter"])
    score_matches(api, de, 2, rng, section=2)

    ffa = tournament("Neon Drift Grand Prix", "Neon Drift", names[:16], bracket_type="ffa", ffa_group_size=4)
    api.call("POST", f"/tournaments/{ffa}/start", {})
    score_matches(api, ffa, 4, rng)
    api.call("POST", f"/tournaments/{ffa}/ffa-advance", {"per_match": True, "keep_count": 2})
    score_matches(api, ffa, 1, rng)

    rr = tournament("Goal Rush League", "Goal Rush", ["RocketQueen", "GlitchMaster", "ArcticFox", "StormBringer", "DragonByte", "VoltStrike"], bracket_type="round_robin")
    api.call("POST", f"/tournaments/{rr}/start", {})
    score_matches(api, rr, 9, rng, draws=True)

    groups = tournament("Kart Frenzy Cup", "Kart Frenzy", names[4:16], bracket_type="single_elim", phases="double", group_size=4, advancers_count=2)
    api.call("POST", f"/tournaments/{groups}/start", {})
    score_matches(api, groups, 14, rng, draws=True)

    teams = tournament("Rocket Duo", "Rocket Duo", names[:12], bracket_type="single_elim", use_teams=True, team_size=2, team_lock_mode="captain_only")
    for team_name, captain in [("Turbo Duo", "PixelHunter"), ("Les Gaulois" if fr else "The Gauls", "LaserCat"), ("Pixel Pair", "ShadowNinja"),
                               ("Night Shift", "CosmicDust"), ("Dream Team", "BlazeRunner"), ("GG EZ", "NightHawk")]:
        api.call("POST", f"/tournaments/{teams}/teams", {"name": team_name}, as_user=captain)
    api.call("POST", f"/tournaments/{teams}/teams/randomize", {})

    closed2 = tournament("Goal Rush Warm-up" if not fr else "Échauffement Goal Rush", "Goal Rush", names[6:14], bracket_type="single_elim")
    api.call("POST", f"/tournaments/{closed2}/start", {})
    score_matches(api, closed2, 99, rng)
    api.call("POST", f"/tournaments/{closed2}/close", {})
    wait_for_summaries(api, "PixelHunter")
    api.call("POST", "/admin/awards/notify", {})

    # Info page and files
    if fr:
        info = """# Bienvenue à l'Alambic LAN 2026 !

Du **vendredi 18 h** au **dimanche 16 h**. Voici l'essentiel pour passer un bon week-end.

## Programme

| Quand | Quoi |
|---|---|
| Vendredi 20 h | Castle Siege Open |
| Samedi 10 h | Iron Arena Showdown |
| Samedi 15 h | Neon Drift Grand Prix |
| Dimanche 11 h | Finales et remise des prix |

## Réseau

- **Wi-Fi :** `AlambicLAN`, mot de passe `distillation`
- **Partage de fichiers :** \\\\serveur-lan\\jeux

## Repas

Petit-déjeuner de 8 h à 10 h, repas chauds à 12 h 30 et à 19 h 30. Le bar reste ouvert toute la journée.

## Règles

> On joue fair-play, on garde sa place propre, et on baisse le son après minuit.
"""
        projector = "# Ce soir\n\n- **20 h** : quarts de finale d'Iron Arena\n- **21 h 30** : pizzas au bar\n- **22 h** : finale surprise sur l'écran principal"
    else:
        info = """# Welcome to Alambic LAN 2026!

From **Friday 6 pm** to **Sunday 4 pm**. Here is what you need for a good weekend.

## Schedule

| When | What |
|---|---|
| Friday 8 pm | Castle Siege Open |
| Saturday 10 am | Iron Arena Showdown |
| Saturday 3 pm | Neon Drift Grand Prix |
| Sunday 11 am | Finals and prize giving |

## Network

- **Wi-Fi:** `AlambicLAN`, password `distillation`
- **File share:** \\\\lan-server\\games

## Meals

Breakfast from 8 to 10 am, hot meals at 12:30 pm and 7:30 pm. The bar stays open all day.

## Rules

> Play fair, keep your seat tidy, and turn the sound down after midnight.
"""
        projector = "# Tonight\n\n- **8 pm**: Iron Arena quarter-finals\n- **9:30 pm**: pizzas at the bar\n- **10 pm**: surprise final on the main screen"
    api.call("PUT", "/admin/config/info_page_content", {"value": info})
    api.call("PUT", "/admin/config/info_spectator_content", {"value": projector})
    api.call("POST", "/dashboard/info/files/upload", file=("neon-drift-patch-1.4.zip", b"demo" * 4000))
    api.call("POST", "/dashboard/info/files/upload", file=("iron-arena-config.cfg", b"demo" * 300))

    # Public chat, private messages
    lines = [
        ("LaserCat", "Quelqu'un chaud pour une revanche sur Iron Arena ?", "Anyone up for an Iron Arena rematch?"),
        ("PixelHunter", "Toujours, mais tu vas encore perdre", "Always, but you will lose again"),
        ("IcePhoenix", "Le bar vient de sortir les pizzas, foncez !", "The bar just brought out the pizzas, go go go!"),
        ("CosmicDust", "**GG** à toute la table 3, super partie", "**GG** to all of table 3, great game"),
        ("ShadowNinja", "@LaserCat c'est toi qui as le casque rouge ?", "@LaserCat are you the one with the red headset?"),
        ("LaserCat", "Oui, table 1, place 7", "Yes, table 1, seat 7"),
    ]
    first = None
    for sender, text_fr, text_en in lines:
        msg = api.call("POST", "/public-chat/messages", {"content": text_fr if fr else text_en}, as_user=sender)
        first = first or msg
        api.call("PUT", "/public-chat/config", {"slowmode_seconds": 0, "enabled": True})
    if first:
        api.call("POST", f"/public-chat/messages/{first['id']}/react", {"emoji": "🔥"}, as_user="PixelHunter")
        api.call("POST", f"/public-chat/messages/{first['id']}/react", {"emoji": "🔥"}, as_user="CyberWolf")
    pm = [
        ("LaserCat", "PixelHunter", "Prêt pour la demi ? Je peux lancer quand tu veux.", "Ready for the semi? I can start whenever you want."),
        ("PixelHunter", "LaserCat", "Je finis mon café et j'arrive, deux minutes.", "Finishing my coffee, two minutes."),
        ("LaserCat", "PixelHunter", "Ça marche, je garde le serveur ouvert.", "Fine, I will keep the server open."),
    ]
    for sender, peer, text_fr, text_en in pm:
        api.call("POST", f"/players/messages/{users[peer]}", {"content": text_fr if fr else text_en}, as_user=sender)
    board = api.call("GET", "/dashboard/stats", as_user="PixelHunter")["leaderboard"]
    rank = next(i for i, row in enumerate(board, 1) if row["username"] == "PixelHunter")
    bracket = api.call("GET", f"/tournaments/{de}")["bracket"]
    me = users["PixelHunter"]
    match = next(m for m in bracket if me in m["p"] and 0 not in m["p"] and not (m.get("score") and all(x is not None for x in m["score"])))
    opponent_id = next(p for p in match["p"] if p != me)
    room_users = api.call("GET", "/room/users")
    opponent = next(u for u in room_users if u["id"] == opponent_id)
    api.call("PUT", "/admin/config/demo_facts", {"value": {
        "rank": rank, "points": board[rank - 1]["points"], "other": board[1 if rank == 1 else 0]["username"], "other_points": board[1 if rank == 1 else 0]["points"],
        "opponent": opponent["username"], "opponent_seat": opponent["seat_id"],
    }})
    print("api seed done")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
