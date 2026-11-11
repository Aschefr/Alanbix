"""The recommended models are the ones the comparison's rules pick, never a hand-made list."""
from app import ia_model_catalog, ia_model_comparison as comp

PERFECT = {t: s["questions"] for t, s in comp.TASKS.items()}


def model(right=None, passes=None, made_up=(0, 90), **extra):
    right = {**PERFECT, **(right or {})}
    return {"name": "m", "memory_gb": 5.0, "seconds": 3.0, "right": right, "passes": passes or [right] * 3,
            "made_up": list(made_up), **extra}


def test_rules_give_the_catalogue():
    res = comp.comparison()
    picked = {name for name in res["labels"].values() if name}
    assert {m["name"] for m in ia_model_catalog.CATALOG} == picked
    for m in ia_model_catalog.CATALOG:
        row = next(r for r in res["models"] if r["name"] == m["name"])
        assert m["tier"] in row["labels"]
        assert m["memory_gb"] == row["memory_gb"]
        assert m["typical_seconds"] == row["seconds"]


def test_no_question_weighs_more_than_two_percent():
    assert comp.QUESTION_MAX <= 0.2 + 1e-9
    assert comp.TIE == 0.8


def test_note_counts_the_majority_answer():
    assert comp.note(model()) == 10.0
    assert comp.note(model({"chat": 19})) == 9.8  # 1 of 20 chat questions, weight 40 %


def test_exclusions_name_their_reason():
    codes = lambda m: [e["code"] for e in comp.exclusions(m)]  # noqa: E731
    assert codes(model(made_up=(2, 90))) == []
    assert codes(model(made_up=(8, 90))) == []        # under 10 % of the flagged answers
    assert codes(model(made_up=(9, 90))) == ["made_up"]
    assert codes(model(made_up=(3, 20))) == ["made_up"]  # 15 %, and 3 times
    assert codes(model({"chat": 13, "public": 15})) == ["chats"]  # 28/35, under 90 %
    low_pass = [PERFECT, {**PERFECT, "notify": 2}, PERFECT]
    assert codes(model(passes=low_pass)) == ["task"]


def test_tie_needs_the_note_and_every_task():
    a = {**model(), "note": 9.6}
    close = {**model({"public": 13}), "note": 9.2}
    assert comp.tied(a, close)
    far_on_a_task = {**model(passes=[{**PERFECT, "public": 10}] * 3), "note": 9.2}
    assert not comp.tied(a, far_on_a_task)  # 5 public questions apart in every pass
    assert not comp.tied(a, {**model(), "note": 8.7})


def test_lightest_tied_model_wins_and_cards_need_room():
    res = comp.comparison()
    # mimo-v2.6:9b has the best note (9.8) but gemma4:e4b (9.2) is tied with it and lighter
    assert res["labels"]["top"] == "gemma4:e4b" and res["labels"]["alternative"] == "mimo-v2.6:9b"
    excluded = {r["name"] for r in res["models"] if r["excluded"]}
    assert excluded == {"qwen3.5:4b", "qwen3.5:9b", "gemma4:e2b"}
    assert all(not r["labels"] for r in res["models"] if r["excluded"])
    for card, name in res["cards"].items():
        assert next(r for r in res["models"] if r["name"] == name)["memory_gb"] <= card - 1


def test_made_up_count_is_shown_for_every_model():
    res = comp.comparison()
    assert res["made_up"] == {"rate": 10, "min": 3, "asked": 90}
    q4 = next(r for r in res["models"] if r["name"] == "qwen3.5:4b")
    assert q4["made_up"] == [18, 90] and q4["excluded"][0]["tasks"] == ["made_up"]
