"""docs/07-classify.md and docs/08-escalating-labels.md.

No model is called. A plain function stands in for each labeler, so what is
tested is everything around the model: what it is sent, where posts are
routed, and what is stored.
"""
import asyncio

import numpy as np
import pytest
from pydantic import ValidationError
from sklearn.linear_model import LogisticRegression

from bluesky_bots.classify import (BASE_INSTRUCTION, build_instruction, build_label_model,
                                   build_tiered_workflow, build_workflow, is_unsure, label_rows,
                                   run_workflow, threshold_table, train_classifier, training_set)

from conftest import make_topic, post_row

TEXTS = {1: "Schumer caved again. Every single time.",        # clearly critical
         2: "Honestly Jeffries handled that well.",           # clearly supportive
         3: "Oh sure, Schumer is a master strategist."}       # sarcasm


@pytest.fixture
def loaded(mem, topic):
    """A store with three posts in the topic and one that is not."""
    mem.add_posts([post_row(n, text=t) for n, t in TEXTS.items()] + [post_row(9, text="Lovely weather.")])
    mem.set_post_topics(topic.name, [{"uri": post_row(n)["uri"], "matched_by": "keyword"} for n in TEXTS])
    return mem


def final(store) -> dict:
    """{post number: (model, value)} from labels_final, ignoring the target."""
    rows = store.analytics().execute("SELECT DISTINCT uri, model, value FROM labels_final").fetchall()
    return {int(uri.rsplit("/", 1)[1]): (model, value) for uri, model, value in rows}


# --- the scheme ------------------------------------------------------------

def test_label_model_follows_the_topic(topic):
    Label = build_label_model(topic)
    ok = Label(i=0, entities=["schumer"], stance="critical")
    assert ok.model_dump() == {"i": 0, "entities": ["schumer"], "stance": "critical"}
    with pytest.raises(ValidationError):
        Label(i=0, entities=["schumer"], stance="furious")          # not an allowed value
    with pytest.raises(ValidationError):
        Label(i=0, entities=["pelosi"], stance="critical")          # not one of the topic's entities
    assert "uri" not in Label.model_fields and "confidence" not in Label.model_fields


def test_label_model_without_entities_and_with_two_dimensions():
    t = make_topic(entities={}, labels={"version": "v1", "instruction": "x", "dimensions": {
        "position": {"values": ["for", "against", "unclear"], "unsure": "unclear"},
        "kind": {"values": ["news", "opinion"]}}})
    Label = build_label_model(t)
    assert set(Label.model_fields) == {"i", "position", "kind"}
    assert is_unsure(t, {"i": 0, "position": "unclear", "kind": "news"})
    assert not is_unsure(t, {"i": 0, "position": "for", "kind": "news"})
    rows = label_rows(t, "at://x/1", {"i": 0, "position": "for", "kind": "news"}, "m", tier=1)
    assert [(r["target"], r["dimension"], r["value"]) for r in rows] == [("", "position", "for"), ("", "kind", "news")]


def test_instruction_always_carries_the_base_rules(topic):
    text = build_instruction(topic)
    assert text.startswith(BASE_INSTRUCTION) and "Test topic." in text
    assert "critical, supportive, neutral, unclear" in text and "schumer, jeffries" in text
    assert 'The "cannot tell" value is unclear' in text


def test_label_rows_one_per_entity(topic):
    rows = label_rows(topic, "at://x/1", {"i": 0, "entities": ["schumer", "jeffries"], "stance": "critical"},
                      "fast", tier=1)
    assert [(r["target"], r["value"], r["scheme_version"], r["tier"]) for r in rows] == [
        ("schumer", "critical", "v1", 1), ("jeffries", "critical", "v1", 1)]
    none = label_rows(topic, "at://x/1", {"i": 0, "entities": [], "stance": "neutral"}, "fast", tier=1)
    assert [r["target"] for r in none] == [""]


# --- one model (docs/07) ---------------------------------------------------

def stand_in(seen: list, rule):
    """A labeler that records what it was sent and answers with rule(text)."""
    def labeler(ctx, node_input):
        seen.append(node_input.model_dump())
        entity = "jeffries" if "Jeffries" in node_input.text else "schumer"
        return {"i": node_input.i, "entities": [entity], "stance": rule(node_input.text)}
    return labeler


def simple(text: str) -> str:
    return "unclear" if "Oh sure" in text else "supportive" if "well" in text else "critical"


def test_workflow_labels_a_topic_and_queues_what_is_unsure(loaded, topic):
    seen = []
    workflow = build_workflow(topic, loaded, model="fast-model", labeler=stand_in(seen, simple))
    message = asyncio.run(run_workflow(workflow, "s1"))
    assert message == "saved 3 label rows for 3 posts"
    assert final(loaded) == {1: ("fast-model", "critical"), 2: ("fast-model", "supportive"),
                             3: ("fast-model", "unclear")}
    assert [r["item_id"] for r in loaded.pending_reviews("post", topic.name)] == [post_row(3)["uri"]]

    assert len(seen) == 3 and all(set(item) == {"i", "text", "parent_text"} for item in seen)
    assert "at://" not in str(seen) and "did:" not in str(seen)     # no uri or DID reaches the model
    assert "weather" not in str(seen)                               # a post outside the topic is never sent

    again = build_workflow(topic, loaded, model="fast-model", labeler=stand_in(seen, simple))
    assert asyncio.run(run_workflow(again, "s2")) == "nothing to classify"
    assert len(seen) == 3


def test_workflow_respects_the_limit(loaded, topic):
    seen = []
    workflow = build_workflow(topic, loaded, model="m", labeler=stand_in(seen, simple))
    assert asyncio.run(run_workflow(workflow, "s1", limit=2)) == "saved 2 label rows for 2 posts"


# --- tiers (docs/08) -------------------------------------------------------

def tiered(store, topic, seen, **settings):
    return build_tiered_workflow(
        topic, store, fast="fast-model", strong="strong-model",
        labelers={"fast": stand_in(seen["fast"], simple),
                  "strong": stand_in(seen["strong"], lambda text: "critical")}, **settings)


def test_tiers_without_a_classifier(loaded, topic):
    seen = {"fast": [], "strong": []}
    message = asyncio.run(run_workflow(tiered(loaded, topic, seen), "t1"))
    assert message == "saved 4 label rows for 3 posts"               # three from tier 1, one from tier 2
    assert len(seen["fast"]) == 3 and [s["text"] for s in seen["strong"]] == [TEXTS[3]]
    assert final(loaded) == {1: ("fast-model", "critical"), 2: ("fast-model", "supportive"),
                             3: ("strong-model", "critical")}
    assert loaded.pending_reviews("post") == []
    assert "at://" not in str(seen)


def test_tiers_send_what_the_strong_model_cannot_tell_to_review(loaded, topic):
    seen = {"fast": [], "strong": []}
    workflow = build_tiered_workflow(topic, loaded, fast="f", strong="s", labelers={
        "fast": stand_in(seen["fast"], simple), "strong": stand_in(seen["strong"], lambda text: "unclear")})
    asyncio.run(run_workflow(workflow, "t1"))
    assert [r["item_id"] for r in loaded.pending_reviews("post", topic.name)] == [post_row(3)["uri"]]


def test_tier_0_settles_what_it_is_sure_of(loaded, topic):
    # Vectors stand in for embeddings: critical posts near (1, 0), supportive near (0, 1),
    # and the sarcastic one in between, so the classifier is unsure of it.
    where = {TEXTS[1]: [1.0, 0.0], TEXTS[2]: [0.0, 1.0], TEXTS[3]: [0.55, 0.45]}
    rng = np.random.default_rng(0)
    x = np.vstack([rng.normal([1, 0], 0.05, (40, 2)), rng.normal([0, 1], 0.05, (40, 2))])
    clf = LogisticRegression(C=100).fit(x, ["critical"] * 40 + ["supportive"] * 40)

    seen = {"fast": [], "strong": []}
    workflow = tiered(loaded, topic, seen, classifiers={"stance": clf}, embed_model="test-embed",
                      embed_fn=lambda texts: np.array([where[t] for t in texts]), threshold=0.9)
    asyncio.run(run_workflow(workflow, "t1"))

    assert [s["text"] for s in seen["fast"]] == [TEXTS[3]]           # only the unsure post reached a model
    got = final(loaded)
    assert got[1] == ("logreg+test-embed", "critical") and got[2] == ("logreg+test-embed", "supportive")
    assert got[3] == ("strong-model", "critical")
    tiers = loaded.analytics().execute(
        "SELECT tier, count(DISTINCT uri) FROM labels GROUP BY 1 ORDER BY 1").fetchall()
    assert tiers == [(0, 3), (1, 1), (2, 1)]                         # every tier keeps its row
    confidence = loaded.analytics().execute(
        "SELECT min(confidence), max(confidence) FROM labels WHERE tier = 0").fetchone()
    assert 0.5 <= confidence[0] < 0.9 < confidence[1] <= 1.0
    assert loaded.analytics().execute("SELECT count(*) FROM labels WHERE tier > 0 AND confidence IS NOT NULL"
                                      ).fetchone()[0] == 0


# --- training tier 0 -------------------------------------------------------

def test_training_set_leaves_out_the_unsure_value(loaded, topic):
    for n, value in ((1, "critical"), (2, "supportive"), (3, "unclear")):
        loaded.save_labels(label_rows(topic, post_row(n)["uri"],
                                      {"i": 0, "entities": ["schumer"], "stance": value}, "strong-model", tier=2))
    rows = training_set(loaded, topic, "stance", "strong-model")
    assert [(r["text"], r["value"]) for r in rows] == [(TEXTS[1], "critical"), (TEXTS[2], "supportive")]
    assert training_set(loaded, topic, "stance", "another-model") == []


def test_train_classifier_and_threshold_table():
    rng = np.random.default_rng(1)
    x = np.vstack([rng.normal([1, 0], 0.4, (120, 2)), rng.normal([0, 1], 0.4, (120, 2))])
    y = ["critical"] * 120 + ["supportive"] * 120
    clf, x_te, y_te = train_classifier(x, y)
    assert len(x_te) == 60 and sorted(clf.classes_) == ["critical", "supportive"]
    table = threshold_table(clf, x_te, y_te)
    settled = [row["settled"] for row in table]
    assert settled == sorted(settled, reverse=True)                  # a higher threshold settles fewer posts
    assert table[0]["accuracy"] > 0.8
