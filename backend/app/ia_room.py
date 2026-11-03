"""Room map helpers for the AI tools: seat names and where things are in the room."""
import json
import math
import re
import unicodedata


def _seat_labeler(db, models):
    """seat_id ("T3_S7") -> "Table 3, place 7", with the table's name as shown on the room map."""
    room = db.query(models.RoomMap).first()
    names = {t.get("id"): t.get("label") or t.get("name") for t in ((room.layout or {}).get("tables") or [])} if room else {}

    def label(seat_id):
        if not seat_id:
            return "Non assigné"
        m = re.match(r"^(T\d+)_S(\d+(?:_\d+)?)$", seat_id)
        if not m:
            return seat_id
        table = names.get(m.group(1)) or f"Table {m.group(1)[1:]}"
        return f"{table}, place {m.group(2)}"
    return label


# --- Where things are in the room ---
# The map is not to scale: a seat (50 px) stands for about 0.8 m of a LAN table, enough for a rough
# distance. Players are guided first with landmarks and a direction, as on the map they see.
SEAT_PX = 50
SEAT_METERS = 0.8

TYPE_NAMES = {
    "door": "Porte", "kitchen": "Cuisine", "bar": "Bar", "wc": "Toilettes", "rack": "Baie réseau",
    "screen": "Écran", "wifi": "Borne Wi-Fi", "generic": "Élément",
}
# Words a player may use for each kind of element (any language of the app, without accents)
TYPE_WORDS = {
    "wifi": ["wifi", "wi-fi", "wi fi", "borne", "point d'acces", "access point", "routeur", "router",
             "sans fil", "wireless", "punto de acceso", "inalambric"],
    "wc": ["wc", "toilette", "toilet", "restroom", "bathroom", "sanitaire", "bano", "aseo"],
    "door": ["porte", "door", "sortie", "exit", "entree", "entrance", "puerta", "salida", "entrada"],
    "bar": ["bar", "boisson", "drink", "buvette", "bebida"],
    "kitchen": ["cuisine", "kitchen", "repas", "manger", "food", "cocina", "comida"],
    "screen": ["ecran", "screen", "projecteur", "projector", "scene", "stage", "pantalla"],
    "rack": ["rack", "baie", "serveur", "server", "switch", "servidor"],
}

PLACES_NOTE = (
    "Le plan n'est pas à l'échelle. Guide le joueur d'abord avec des repères et une direction générale, "
    "comme sur le plan qu'il voit dans l'application (par exemple « entre la Table 2 et la Table 3, vers la droite »). "
    "N'ajoute une distance (« environ 5 mètres ») qu'en complément si elle aide, jamais en premier ni au mètre près."
)
WIFI_NOTE = " Tu sais où est la borne, pas la qualité du signal : ne promets pas qu'il sera meilleur."


def _plain(text) -> str:
    text = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn").strip()


def _center(o, size=None):
    w = size if size is not None else o.get("w", 0)
    h = size if size is not None else o.get("h", 0)
    return o.get("x", 0) + w / 2, o.get("y", 0) + h / 2


def _gap_to_rect(px, py, r):
    """Distance from a point to the edge of a rectangle (0 inside)."""
    dx = max(r.get("x", 0) - px, 0, px - (r.get("x", 0) + r.get("w", 0)))
    dy = max(r.get("y", 0) - py, 0, py - (r.get("y", 0) + r.get("h", 0)))
    return math.hypot(dx, dy)


def _direction(dx, dy) -> str:
    """Direction on the map (x to the right, y downwards), in words."""
    names = ["vers la droite", "vers le bas à droite", "vers le bas", "vers le bas à gauche",
             "vers la gauche", "vers le haut à gauche", "vers le haut", "vers le haut à droite"]
    return names[round(math.degrees(math.atan2(dy, dx)) / 45) % 8]


def _zone(x, y, bounds) -> str:
    """Area of the room: "côté droit de la salle", "en haut à gauche de la salle", "au centre de la salle"…"""
    x0, y0, x1, y1 = bounds
    col = 0 if x < x0 + (x1 - x0) / 3 else 2 if x > x0 + 2 * (x1 - x0) / 3 else 1
    row = 0 if y < y0 + (y1 - y0) / 3 else 2 if y > y0 + 2 * (y1 - y0) / 3 else 1
    if (row, col) == (1, 1):
        return "au centre de la salle"
    if row == 1:
        return "côté gauche de la salle" if col == 0 else "côté droit de la salle"
    if col == 1:
        return "en haut de la salle" if row == 0 else "en bas de la salle"
    return f"en {'haut' if row == 0 else 'bas'} à {'gauche' if col == 0 else 'droite'} de la salle"


def _meters(px) -> int:
    return max(1, round(px / SEAT_PX * SEAT_METERS))


def _tool_get_room_places(db, models, args: dict, user_id: int) -> str:
    """Room elements (Wi-Fi access point, toilets, door, bar…): landmarks, direction from the
    player's seat, rough distance and, on request, the nearest free seats."""
    room = db.query(models.RoomMap).first()
    layout = (room.layout or {}) if room else {}
    tables = layout.get("tables") or []
    seats = layout.get("seats") or []
    furniture = layout.get("furniture") or []
    if not furniture:
        return json.dumps({"places": [], "note": "Aucun élément (porte, toilettes, borne Wi-Fi…) n'est placé sur le plan de salle. Dis-le au joueur : un administrateur peut les ajouter."}, ensure_ascii=False)

    def name_of(f):
        return (f.get("label") or "").strip() or TYPE_NAMES.get(f.get("type"), "Élément")

    def table_name(t):
        return t.get("label") or t.get("id")

    query = _plain(args.get("place"))
    if query:
        found = [f for f in furniture
                 if any(w in query for w in TYPE_WORDS.get(f.get("type"), []))
                 or (_plain(name_of(f)) and (_plain(name_of(f)) in query or query in _plain(name_of(f))))]
        if not found:
            return json.dumps({
                "places": [],
                "note": f"Rien ne correspond à « {args.get('place')} » sur le plan de salle. Dis-le au joueur franchement, sans inventer d'emplacement.",
                "elements_on_map": sorted({name_of(f) for f in furniture}),
            }, ensure_ascii=False)
    else:
        found = furniture

    xs, ys = [], []
    for o in tables + furniture:
        xs += [o.get("x", 0), o.get("x", 0) + o.get("w", 0)]
        ys += [o.get("y", 0), o.get("y", 0) + o.get("h", 0)]
    for s in seats:
        xs += [s.get("x", 0), s.get("x", 0) + SEAT_PX]
        ys += [s.get("y", 0), s.get("y", 0) + SEAT_PX]
    bounds = (min(xs), min(ys), max(xs), max(ys))

    label = _seat_labeler(db, models)
    user = db.query(models.User).filter(models.User.id == user_id).first() if user_id else None
    my_seat = next((s for s in seats if user and s.get("id") == user.seat_id), None)
    occupied = {u.seat_id for u in db.query(models.User).filter(models.User.seat_id.isnot(None)).all()}

    places = []
    for f in found:
        cx, cy = _center(f)
        where = _zone(cx, cy, bounds)
        near = sorted(tables, key=lambda t: _gap_to_rect(cx, cy, t))
        if near:
            d1 = _gap_to_rect(cx, cy, near[0])
            if len(near) > 1 and _gap_to_rect(cx, cy, near[1]) <= 1.6 * d1 + SEAT_PX:
                # "entre Table 2 et Table 3": in the tables' own order, numbers compared as numbers
                pair = sorted(near[:2], key=lambda t: [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", table_name(t))])
                where = f"entre {table_name(pair[0])} et {table_name(pair[1])}, {where}"
            else:
                tx, ty = _center(near[0])
                side = _direction(cx - tx, cy - ty).replace("vers ", "")
                where = f"près de {table_name(near[0])} ({side} de celle-ci), {where}"
        place = {"name": name_of(f), "kind": f.get("type"), "where": where}
        if my_seat:
            sx, sy = _center(my_seat, SEAT_PX)
            dist = math.hypot(cx - sx, cy - sy)
            place["from_player_seat"] = f"{_direction(cx - sx, cy - sy)} sur le plan, environ {_meters(dist)} m"
            place["_dist"] = dist
        if args.get("free_seats"):
            free = [s for s in seats if s.get("id") not in occupied]
            free.sort(key=lambda s: math.hypot(_center(s, SEAT_PX)[0] - cx, _center(s, SEAT_PX)[1] - cy))
            place["nearest_free_seats"] = [label(s["id"]) for s in free[:3]]
        places.append(place)

    places.sort(key=lambda p: p.get("_dist", 0))
    for p in places:
        p.pop("_dist", None)
    note = PLACES_NOTE + (WIFI_NOTE if any(p["kind"] == "wifi" for p in places) else "")
    return json.dumps({"player_seat": label(my_seat["id"]) if my_seat else None, "places": places, "note": note}, ensure_ascii=False)
