"""Room map helpers for the AI tools: seat names and where things are in the room."""
import re


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
