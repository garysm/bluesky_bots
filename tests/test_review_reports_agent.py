"""docs/11-review.md, docs/12-agent.md and docs/13-reports.md.

ANON_SALT is set for the test run by conftest-free means: each test that
needs it passes through the `salted` fixture.
"""
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from bluesky_bots.agent import build_analyst, tools
from bluesky_bots.privacy import anon_id
from bluesky_bots.reports import FORBIDDEN, export_public, label_chart, label_counts_by_day
from bluesky_bots.review import decide_account, decide_post, pending_accounts, pending_posts, queue_flagged
from bluesky_bots.topics import get_topic

from conftest import make_topic, post_row

DAY = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)


@pytest.fixture
def salted(monkeypatch):
    monkeypatch.setenv("ANON_SALT", "a-test-secret")


def flag(store, did):
    """Give an account two different signals, which puts it in the flagged view."""
    store.upsert_accounts([{"did": did}])
    store.save_signals([{"did": did, "signal": "burst", "value": 16, "evidence": {"posts": 16}},
                        {"did": did, "signal": "account_age", "value": 2, "evidence": {"age_days_at_first_post": 2}}])


def label(store, topic, n, value, did="did:plc:a", day=DAY, entity="schumer", model="fast", tier=1):
    row = post_row(n, did=did, created_at=day)
    store.add_posts([row])
    store.save_labels([{"uri": row["uri"], "topic": topic.name, "scheme_version": topic.labels.version,
                        "model": model, "target": entity, "dimension": "stance", "value": value, "tier": tier}])
    return row["uri"]


# --- privacy and export (docs/13) ------------------------------------------

def test_anon_id_is_stable_and_depends_on_the_salt(salted, monkeypatch):
    a = anon_id("did:plc:someone")
    assert a == anon_id("did:plc:someone") and a.startswith("acct_") and len(a) == 17
    assert "someone" not in a and a != anon_id("did:plc:other")
    assert a != anon_id("did:plc:someone", salt="another-secret")
    monkeypatch.delenv("ANON_SALT")
    with pytest.raises(RuntimeError):
        anon_id("did:plc:someone")


def test_export_public_refuses_identifying_columns(tmp_path):
    for column in sorted(FORBIDDEN):
        frame = pd.DataFrame({"day": ["2026-11-05"], "n": [50], column: ["x"]})
        with pytest.raises(ValueError, match=column):
            export_public(frame, tmp_path / "x.csv", count_col="n")
    assert not (tmp_path / "x.csv").exists()


def test_export_public_hides_small_counts(tmp_path):
    frame = pd.DataFrame({"day": ["2026-11-05", "2026-11-06", "2026-11-07"], "n": [50, 9, 10]})
    written = export_public(frame, tmp_path / "daily.csv", count_col="n")
    assert written["n"].tolist() == [50, 10]
    assert pd.read_csv(tmp_path / "daily.csv")["n"].tolist() == [50, 10]


# --- the chart (docs/13) ---------------------------------------------------

def test_label_counts_by_day(mem, topic):
    flag(mem, "did:plc:flagged")
    mem.upsert_accounts([{"did": "did:plc:bot", "self_declared_bot": True}])
    label(mem, topic, 1, "critical")
    label(mem, topic, 2, "critical", did="did:plc:flagged")
    label(mem, topic, 3, "critical", did="did:plc:bot")
    label(mem, topic, 4, "supportive")
    label(mem, topic, 5, "critical", entity="jeffries")
    label(mem, topic, 6, "critical", day=DAY + timedelta(days=1, hours=11, minutes=59))
    label(mem, topic, 7, "critical", day=DAY + timedelta(days=2))          # outside the range asked for
    both = label(mem, topic, 8, "critical")                                # one post about both entities
    mem.save_labels([{"uri": both, "topic": topic.name, "scheme_version": "v1", "model": "fast",
                      "target": "jeffries", "dimension": "stance", "value": "critical", "tier": 1}])

    con = mem.analytics()
    df = label_counts_by_day(con, topic, "stance", "critical", "2026-11-05", "2026-11-06")
    assert df["day"].astype(str).tolist() == ["2026-11-05", "2026-11-06"]
    assert df["all_accounts"].tolist() == [5, 1]                           # a post is counted once
    assert df["excluding_flagged"].tolist() == [4, 1]
    assert df["self_declared_bots"].tolist() == [1, 0]
    assert (df["excluding_flagged"] <= df["all_accounts"]).all()

    about = label_counts_by_day(con, topic, "stance", "critical", "2026-11-05", "2026-11-05", target="jeffries")
    assert about["all_accounts"].tolist() == [2]


def test_label_chart_has_three_lines_and_the_topic_markers(mem):
    topic = make_topic(title="Test topic", markers=[{"date": date(2026, 11, 3), "label": "Election day"}])
    label(mem, topic, 1, "critical")
    df, fig = label_chart(mem.analytics(), topic, "stance", "critical", "2026-11-01", "2026-11-30", target="schumer")
    assert [trace.name for trace in fig.data] == ["all_accounts", "excluding_flagged", "self_declared_bots"]
    assert len(fig.layout.shapes) == 1 and "Election day" in str(fig.layout.annotations)
    assert "Test topic" in fig.layout.title.text and "schumer" in fig.layout.title.text
    assert len(df) == 1


# --- review (docs/11) ------------------------------------------------------

def test_accounts_are_reviewed_under_an_anonymous_id(mem, salted):
    flag(mem, "did:plc:suspect")
    assert queue_flagged(mem) == 1 and queue_flagged(mem) == 1             # queueing twice adds nothing
    (item,) = pending_accounts(mem)
    assert item["account"] == anon_id("did:plc:suspect") and "did:" not in str(item)
    assert [e["signal"] for e in item["evidence"]] == ["account_age", "burst"]
    assert item["evidence"][1]["observed"] == {"posts": 16}

    with pytest.raises(ValueError):
        decide_account(mem, item["account"], "gm", "guilty")
    with pytest.raises(KeyError):
        decide_account(mem, "acct_000000000000", "gm", "not_coordinated")
    decide_account(mem, item["account"], "gm", "not_coordinated", notes="a news outlet's live coverage")
    assert pending_accounts(mem) == []
    assert mem.analytics().execute("SELECT count(*) FROM flagged").fetchone()[0] == 0
    (review,) = mem.export_table("reviews")
    assert (review["did"], review["decision"], review["reviewer"]) == ("did:plc:suspect", "not_coordinated", "gm")


def test_a_persons_label_wins_over_every_model(mem, topic):
    uri = label(mem, topic, 1, "unclear", model="strong", tier=2)
    mem.set_post_topics(topic.name, [{"uri": uri, "matched_by": "keyword"}])
    mem.enqueue_review([{"item_type": "post", "item_id": uri, "topic": topic.name, "reason": "no model could tell"}])
    (item,) = pending_posts(mem, topic)
    assert item["text"] == "hello" and item["labels"] == [{"target": "schumer", "dimension": "stance", "value": "unclear"}]

    with pytest.raises(ValueError):
        decide_post(mem, topic, uri, "gm", {"stance": "furious"})
    decide_post(mem, topic, uri, "gm", {"stance": "critical"}, target="schumer")
    assert pending_posts(mem, topic) == []
    final = mem.analytics().execute("SELECT model, value, tier FROM labels_final").fetchall()
    assert final == [("human:gm", "critical", 9)]
    assert len(list(mem.export_table("labels"))) == 2                      # the model's answer is kept beside it


# --- agent tools (docs/12) -------------------------------------------------

@pytest.fixture
def tool_store(mem, monkeypatch):
    @contextmanager
    def session():
        yield mem.analytics()
    monkeypatch.setattr(tools, "_session", session)
    return mem


def test_list_topics_describes_what_can_be_asked():
    listed = {t["name"]: t for t in tools.list_topics()}
    assert listed["dem-leadership"]["dimensions"] == {"stance": ["critical", "supportive", "neutral", "unclear"]}
    assert listed["dem-leadership"]["entities"] == ["schumer", "jeffries"]


def test_label_counts_tool_returns_aggregates_only(tool_store):
    topic = get_topic("dem-leadership")
    flag(tool_store, "did:plc:flagged")
    label(tool_store, topic, 1, "critical")
    label(tool_store, topic, 2, "critical", did="did:plc:flagged")
    label(tool_store, topic, 3, "supportive", entity="jeffries")
    rows = tools.label_counts_by_day(" Dem-Leadership ", "Stance", "2026-11-05", "2026-11-05")
    assert rows == [{"day": "2026-11-05", "value": "critical", "n_all": 2, "n_unflagged": 1},
                    {"day": "2026-11-05", "value": "supportive", "n_all": 1, "n_unflagged": 1}]
    assert all(row["n_unflagged"] <= row["n_all"] for row in rows)
    assert "did:" not in str(rows) and "at://" not in str(rows)
    only = tools.label_counts_by_day("dem-leadership", "stance", "2026-11-05", "2026-11-05", entity="Jeffries")
    assert [(r["value"], r["n_all"]) for r in only] == [("supportive", 1)]
    assert tools.label_counts_by_day("dem-leadership", "stance", "2026-01-01", "2026-01-02") == []


def test_narrative_share_tool(tool_store):
    for day, sizes in ((date(2026, 11, 4), [10, 10]), (date(2026, 11, 5), [60, 30, 10])):
        tool_store.save_narratives("dem-leadership", day, [
            {"narrative_id": i, "name": f"narrative {i}", "summary": "s", "n_posts": n}
            for i, n in enumerate(sizes)], [])
    latest = tools.narrative_share("dem-leadership")
    assert [(r["name"], r["share_pct"]) for r in latest] == [("narrative 0", 60.0), ("narrative 1", 30.0), ("narrative 2", 10.0)]
    assert len(tools.narrative_share("dem-leadership", top_n=2)) == 2
    assert [r["share_pct"] for r in tools.narrative_share("dem-leadership", "2026-11-04")] == [50.0, 50.0]


def test_the_analyst_has_only_the_aggregate_tools():
    analyst = build_analyst(model="gemini-flash-lite-latest")              # built, never called
    assert [tool.__name__ for tool in analyst.tools] == ["list_topics", "label_counts_by_day", "narrative_share"]
    assert "Never mention individual accounts" in analyst.instruction
