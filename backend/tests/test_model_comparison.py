"""The recommended models are the ones the comparison's rules pick, never a hand-made list."""
from app import ia_model_catalog, ia_model_comparison as comp


def test_rules_give_the_catalogue():
    res = comp.comparison()
    picked = {name for name in res["labels"].values() if name}
    assert {m["name"] for m in ia_model_catalog.CATALOG} == picked
    for m in ia_model_catalog.CATALOG:
        row = next(r for r in res["models"] if r["name"] == m["name"])
        assert m["tier"] in row["labels"]
        assert m["memory_gb"] == row["memory_gb"]
        assert m["typical_seconds"] == round(row["seconds"])


def test_note_weights_each_task():
    perfect = {"passes": [{t: s["questions"] for t, s in comp.TASKS.items()}] * 2}
    assert comp.note(perfect) == 10.0
    one_chat_miss = {"passes": [perfect["passes"][0], {**perfect["passes"][0], "chat": 12}]}
    assert comp.note(one_chat_miss) == 9.8  # 1 of 26 chat answers, weight 40 %


def test_exclusions_name_their_reason():
    ok = {t: s["questions"] for t, s in comp.TASKS.items()}
    assert comp.exclusions({"passes": [ok, ok], "made_up": 2}) == []  # up to twice is tolerated
    codes = lambda m: [e["code"] for e in comp.exclusions(m)]  # noqa: E731
    assert codes({"passes": [ok, ok], "made_up": 3}) == ["made_up"]
    assert codes({"passes": [ok, {**ok, "chat": 9}], "made_up": 0}) == ["chats"]  # 34/38
    assert codes({"passes": [ok, {**ok, "notify": 0}], "made_up": 0}) == ["task"]


def test_tie_goes_to_the_lightest_and_cards_need_room():
    res = comp.comparison()
    # qwen3.8:27b scores 10.0 but gemma4:e4b (9.8) is within the tie and far lighter
    assert res["labels"]["top"] == "gemma4:e4b"
    e2b = next(r for r in res["models"] if r["name"] == "gemma4:e2b")
    assert e2b["excluded"] and not e2b["labels"]
    assert all(r["memory_gb"] <= card - 1 for card, name in res["cards"].items() for r in res["models"] if r["name"] == name)
