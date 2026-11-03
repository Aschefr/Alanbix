import json

from app import models
from app.ia_room import _tool_get_room_places

# Same shape as the dev room: Table 2 top right, Table 3 below it, the access point between them on the right
LAYOUT = {
    "tables": [
        {"id": "T1", "label": "Table 1", "x": 100, "y": 80, "w": 260, "h": 140},
        {"id": "T2", "label": "Table 2", "x": 520, "y": 80, "w": 200, "h": 140},
        {"id": "T3", "label": "Table 3", "x": 560, "y": 320, "w": 200, "h": 140},
    ],
    "seats": [
        {"id": "T1_S1", "x": 115, "y": 35}, {"id": "T1_S2", "x": 175, "y": 35},
        {"id": "T2_S1", "x": 535, "y": 35}, {"id": "T2_S2", "x": 595, "y": 35}, {"id": "T2_S3", "x": 655, "y": 225},
        {"id": "T3_S1", "x": 575, "y": 275}, {"id": "T3_S2", "x": 695, "y": 275},
    ],
    "furniture": [
        {"id": "F1", "type": "wifi", "label": "Borne Wi-Fi", "x": 780, "y": 240, "w": 60, "h": 60},
        {"id": "F2", "type": "wc", "label": "WC", "x": 0, "y": 440, "w": 80, "h": 80},
    ],
}


def setup_room(db, seat="T1_S1"):
    db.add(models.RoomMap(layout=LAYOUT))
    player = db.query(models.User).filter(models.User.username == "Player1").first()
    player.seat_id = seat
    db.query(models.User).filter(models.User.username == "Player2").first().seat_id = "T3_S2"
    db.commit()
    return player


def ask(db, user, **args):
    return json.loads(_tool_get_room_places(db, models, args, user.id))


def test_wifi_between_two_tables_with_direction_and_free_seats(db_session):
    player = setup_room(db_session)
    res = ask(db_session, player, place="je cherche le wifi", free_seats=True)
    assert res["player_seat"] == "Table 1, place 1"
    [ap] = res["places"]
    assert ap["kind"] == "wifi"
    assert ap["where"].startswith("entre Table 2 et Table 3")
    assert ap["where"].endswith("côté droit de la salle")
    assert ap["from_player_seat"].startswith("vers le bas à droite") or ap["from_player_seat"].startswith("vers la droite")
    assert "environ" in ap["from_player_seat"]
    # Free seats closest to the access point; T3_S2 is taken by Player2
    assert ap["nearest_free_seats"][0] == "Table 2, place 3"
    assert "Table 3, place 2" not in ap["nearest_free_seats"]
    assert "direction" in res["note"] and "qualité du signal" in res["note"]


def test_toilets_found_in_another_language_and_sorted_by_distance(db_session):
    player = setup_room(db_session)
    assert ask(db_session, player, place="restroom")["places"][0]["kind"] == "wc"
    every = ask(db_session, player)["places"]
    assert [p["kind"] for p in every] == ["wc", "wifi"]  # the toilets are closer to Table 1


def test_nothing_matching_is_said_plainly(db_session):
    player = setup_room(db_session)
    res = ask(db_session, player, place="bar")
    assert res["places"] == []
    assert "sans inventer" in res["note"]
    assert set(res["elements_on_map"]) == {"Borne Wi-Fi", "WC"}


def test_player_without_seat_and_empty_room(db_session):
    player = db_session.query(models.User).filter(models.User.username == "Player3").first()
    assert "Aucun élément" in ask(db_session, player, place="wifi")["note"]
    setup_room(db_session)
    res = ask(db_session, player, place="wifi")
    assert res["player_seat"] is None
    assert "from_player_seat" not in res["places"][0]


def test_public_chat_can_use_it():
    from app.ia_public_chat import public_tools
    assert "get_room_places" in {t["function"]["name"] for t in public_tools({})}
