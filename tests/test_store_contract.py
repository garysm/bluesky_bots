"""The storage contract: what every backend must do. docs/05-storage.md

Each test runs once per backend (the `store` fixture). SQLite passes from the
start. DuckDB passes as bluesky_bots/storage/duckdb_store.py is written, a
page at a time. Each test is marked with the page that builds what it needs:

    pytest tests/test_store_contract.py -m page05 -k duckdb
"""
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from bluesky_bots.storage import HUMAN_TIER, SCHEMA, copy_store, open_store

from conftest import post_row

URI = post_row(1)["uri"]


def count(store, table) -> int:
    return len(list(store.export_table(table)))


def label(uri=URI, **changes) -> dict:
    row = {"uri": uri, "topic": "t", "scheme_version": "v1", "model": "fast", "target": "",
           "dimension": "stance", "value": "critical", "confidence": None, "tier": 1}
    row.update(changes)
    return row


# --- docs/05-storage.md ---------------------------------------------------

@pytest.mark.page05
def test_loading_twice_changes_nothing(store):
    rows = [post_row(1), post_row(2)]
    store.add_posts(rows)
    store.add_posts(rows)
    assert count(store, "posts") == 2
    repost = {"uri": "at://did:plc:a/app.bsky.feed.repost/1", "did": "did:plc:a",
              "subject_uri": URI, "created_at": "2026-11-05T00:00:00Z"}
    store.add_reposts([repost])
    store.add_reposts([repost])
    assert count(store, "reposts") == 1


@pytest.mark.page05
def test_values_come_back_in_the_promised_form(store):
    store.add_posts([post_row(1, created_at="2026-11-05T00:01:00.250Z", lang=None)])
    (row,) = store.iter_posts()
    assert row["created_at"] == datetime(2026, 11, 5, 0, 1, 0, 250000, tzinfo=timezone.utc)
    assert row["created_at"].utcoffset() == timedelta(0)
    assert row["lang"] is None and row["reply_parent"] is None and row["text"] == "hello"


@pytest.mark.page05
def test_a_malformed_date_is_stored_as_missing(store):
    store.add_posts([post_row(1, created_at="not a date")])
    assert next(iter(store.iter_posts()))["created_at"] is None


@pytest.mark.page05
def test_upsert_accounts_keeps_what_is_not_given(store):
    store.upsert_accounts([{"did": "did:plc:a", "handle": "a.example", "is_watchlist": True}])
    store.upsert_accounts([{"did": "did:plc:a", "created_at": "2024-01-01T00:00:00Z"}])
    store.upsert_accounts([{"did": "did:plc:b"}])
    rows = {r["did"]: r for r in store.export_table("accounts")}
    a = rows["did:plc:a"]
    assert a["handle"] == "a.example" and a["is_watchlist"] is True
    assert a["created_at"] == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert rows["did:plc:b"]["is_watchlist"] is False and rows["did:plc:b"]["self_declared_bot"] is False


@pytest.mark.page05
def test_topic_membership_is_replaced_and_fetched_in_time_order(store):
    parent = post_row(1, text="the original")
    store.add_posts([parent, post_row(3, text="later"),
                     post_row(2, text="a reply", reply_parent=parent["uri"])])
    store.set_post_topics("t", [{"uri": post_row(n)["uri"], "matched_by": "keyword"} for n in (1, 2, 3)])
    store.set_post_topics("other", [{"uri": parent["uri"], "matched_by": "account"}])
    got = store.posts_in_topic("t")
    assert [p["text"] for p in got] == ["the original", "a reply", "later"]
    assert [p["parent_text"] for p in got] == [None, "the original", None]
    since = datetime(2026, 11, 5, 0, 2, tzinfo=timezone.utc)
    assert [p["text"] for p in store.posts_in_topic("t", since=since)] == ["a reply", "later"]
    assert [p["text"] for p in store.posts_in_topic("t", until=since)] == ["the original"]

    store.set_post_topics("t", [{"uri": parent["uri"], "matched_by": "keyword"}])
    assert [p["text"] for p in store.posts_in_topic("t")] == ["the original"]
    assert [p["text"] for p in store.posts_in_topic("other")] == ["the original"]


@pytest.mark.page05
def test_a_delete_removes_the_post_and_its_membership(store):
    keep = post_row(2)["uri"]
    store.add_posts([post_row(1), post_row(2)])
    repost = URI.replace("post", "repost")
    store.add_reposts([{"uri": repost, "did": "did:plc:a", "subject_uri": keep, "created_at": "2026-11-05T00:00:00Z"}])
    store.set_post_topics("t", [{"uri": URI, "matched_by": "keyword"}, {"uri": keep, "matched_by": "keyword"}])
    store.delete_record(URI)
    store.delete_record(repost)
    store.delete_record("at://did:plc:nobody/app.bsky.feed.post/never-stored")   # not an error
    assert [r["uri"] for r in store.export_table("posts")] == [keep]
    assert [r["uri"] for r in store.export_table("post_topic")] == [keep]
    assert count(store, "reposts") == 0


@pytest.mark.page05
def test_posts_can_be_copied_to_another_backend(store):
    store.add_posts([post_row(1), post_row(2, created_at=None)])
    store.upsert_accounts([{"did": "did:plc:a", "is_watchlist": True}])
    store.set_post_topics("t", [{"uri": URI, "matched_by": "keyword"}])
    for other in ("sqlite", "duckdb"):
        copy = open_store(f"{other}://:memory:")
        for table in ("posts", "accounts", "post_topic"):
            copy.import_table(table, store.export_table(table))
            copy.import_table(table, store.export_table(table))             # importing twice adds nothing
            assert sorted(copy.export_table(table), key=str) == sorted(store.export_table(table), key=str)
        copy.close()


@pytest.mark.complete
def test_a_delete_reaches_every_table(store):
    keep = post_row(2)["uri"]
    store.add_posts([post_row(1), post_row(2)])
    store.add_reposts([{"uri": URI.replace("post", "repost"), "did": "did:plc:a", "subject_uri": keep,
                        "created_at": "2026-11-05T00:00:00Z"}])
    for uri in (URI, keep):
        store.set_post_topics("t" + uri[-1], [{"uri": uri, "matched_by": "keyword"}])
        store.save_labels([label(uri)])
        store.save_vectors("m", {uri: np.ones(3, dtype=np.float32)})
        store.enqueue_review([{"item_type": "post", "item_id": uri, "topic": "t", "reason": "unsure"}])
    store.save_narratives("t", date(2026, 11, 5), [{"narrative_id": 0, "name": "n", "summary": "s", "n_posts": 2}],
                          [{"uri": URI, "narrative_id": 0}, {"uri": keep, "narrative_id": 0}])

    store.delete_record(URI)
    store.delete_record(URI.replace("post", "repost"))
    store.delete_record("at://did:plc:nobody/app.bsky.feed.post/never-stored")   # not an error

    for table in ("posts", "post_topic", "labels", "embeddings", "post_narrative"):
        assert [r["uri"] for r in store.export_table(table)] == [keep], table
    assert count(store, "reposts") == 0
    assert [r["item_id"] for r in store.pending_reviews("post")] == [keep]


@pytest.mark.complete
def test_every_table_can_be_copied_to_another_backend(store):
    store.add_posts([post_row(1), post_row(2, created_at=None)])
    store.upsert_accounts([{"did": "did:plc:a", "is_watchlist": True}])
    store.save_labels([label()])
    store.save_vectors("m", {URI: np.arange(4, dtype=np.float32) / 3})
    store.save_narratives("t", date(2026, 11, 5), [{"narrative_id": 0, "name": "n", "summary": "s", "n_posts": 1}],
                          [{"uri": URI, "narrative_id": 0}])
    store.save_signals([{"did": "did:plc:a", "signal": "burst", "value": 15, "evidence": {"posts": 15}}])
    for other in ("sqlite", "duckdb"):
        copy = open_store(f"{other}://:memory:")
        counts = copy_store(store, copy)
        assert counts["posts"] == 2 and counts["labels"] == 1
        for table in SCHEMA:
            a, b = list(store.export_table(table.name)), list(copy.export_table(table.name))
            assert len(a) == len(b), table.name
            for ra, rb in zip(sorted(a, key=str), sorted(b, key=str)):
                for col in table.columns:
                    if table.columns[col] == "vector":
                        assert np.array_equal(ra[col], rb[col])
                    else:
                        assert ra[col] == rb[col], (table.name, col)
        copy.close()


@pytest.mark.page05
def test_analysis_sql_sees_typed_tables(store):
    store.add_posts([post_row(n) for n in range(30)])
    con = store.analytics()
    rows = con.execute("""
        SELECT time_bucket(INTERVAL '10 minutes', created_at) AS win, count(*) AS n
        FROM posts GROUP BY 1 ORDER BY 1""").fetchall()
    assert [n for _, n in rows] == [10, 10, 10]
    assert rows[0][0].hour == 0                     # the session is in UTC, not this PC's zone
    assert con.execute("SELECT count(*) FROM accounts WHERE is_watchlist").fetchone()[0] == 0


# --- docs/07-classify.md and docs/08-escalating-labels.md ------------------

@pytest.mark.page07
def test_unlabeled_posts(store):
    store.add_posts([post_row(1), post_row(2), post_row(3)])
    store.set_post_topics("t", [{"uri": post_row(n)["uri"], "matched_by": "keyword"} for n in (1, 2)])
    store.save_labels([label(post_row(1)["uri"], model="fast")])
    two = post_row(2)["uri"]
    assert [p["uri"] for p in store.unlabeled_posts("t", "v1")] == [two]
    assert [p["uri"] for p in store.unlabeled_posts("t", "v1", model="strong")] == [URI, two]
    assert len(store.unlabeled_posts("t", "v2")) == 2          # a new scheme version starts again
    assert len(store.unlabeled_posts("t", "v2", limit=1)) == 1
    assert store.unlabeled_posts("nothing-here", "v1") == []


@pytest.mark.page07
def test_saving_a_label_again_replaces_it(store):
    store.add_posts([post_row(1)])
    store.save_labels([label(value="neutral")])
    store.save_labels([label(value="critical")])
    (row,) = store.export_table("labels")
    assert row["value"] == "critical" and row["target"] == "" and row["labeled_at"] is not None


@pytest.mark.page07
def test_labels_final_keeps_the_highest_tier(store):
    store.add_posts([post_row(1)])
    store.save_labels([label(model="logreg", tier=0, value="neutral", confidence=0.7),
                       label(model="fast", tier=1, value="unclear"),
                       label(model="strong", tier=2, value="critical"),
                       label(model="fast", tier=1, value="supportive", target="jeffries")])
    con = store.analytics()
    got = con.execute("SELECT target, model, value FROM labels_final ORDER BY target").fetchall()
    assert got == [("", "strong", "critical"), ("jeffries", "fast", "supportive")]

    store.save_labels([label(model="human:gm", tier=HUMAN_TIER, value="neutral")])
    got = store.analytics().execute("SELECT value FROM labels_final WHERE target = ''").fetchall()
    assert got == [("neutral",)]


# --- docs/09-narratives.md -------------------------------------------------

@pytest.mark.page09
def test_vectors_round_trip(store):
    a, b = np.arange(5, dtype=np.float32) / 7, np.ones(5, dtype=np.float32)
    store.save_vectors("m", {"at://x/1": a, "at://x/2": b})
    store.save_vectors("m", {"at://x/2": a})                    # saving again replaces
    store.save_vectors("other-model", {"at://x/1": b})
    store.save_vectors("m", {})
    got = store.load_vectors("m")
    assert set(got) == {"at://x/1", "at://x/2"}
    assert got["at://x/1"].dtype == np.float32 and np.array_equal(got["at://x/2"], a)
    assert set(store.load_vectors("m", ["at://x/2", "at://x/missing"])) == {"at://x/2"}
    assert store.load_vectors("m", []) == {}


@pytest.mark.page09
def test_narrative_runs(store):
    assert store.narrative_run("t") is None
    for day, name in ((date(2026, 11, 4), "old"), (date(2026, 11, 5), "new")):
        store.save_narratives("t", day, [{"narrative_id": 1, "name": name, "summary": "s", "n_posts": 2}],
                              [{"uri": "at://x/1", "narrative_id": 1}, {"uri": "at://x/2", "narrative_id": 1}])
    store.save_narratives("t", date(2026, 11, 5), [{"narrative_id": 1, "name": "redone", "summary": "s", "n_posts": 1}],
                          [{"uri": "at://x/1", "narrative_id": 1}])         # the same day again replaces it
    run = store.narrative_run("t")
    assert run["run_date"] == date(2026, 11, 5)
    assert [n["name"] for n in run["narratives"]] == ["redone"]
    assert run["assignments"] == [{"uri": "at://x/1", "narrative_id": 1}]
    assert store.narrative_run("t", before=date(2026, 11, 5))["narratives"][0]["name"] == "old"
    assert store.narrative_run("t", before=date(2026, 11, 4)) is None


# --- docs/10-signals.md and docs/11-review.md ------------------------------

@pytest.mark.page10
def test_flagged_needs_two_different_signals(store):
    store.upsert_accounts([{"did": d} for d in ("did:plc:one", "did:plc:two", "did:plc:listed", "did:plc:cleared")])
    store.upsert_accounts([{"did": "did:plc:listed", "is_watchlist": True}])
    rows = [{"did": "did:plc:one", "signal": "burst", "value": 15, "evidence": {"posts": 15}},
            {"did": "did:plc:one", "signal": "burst", "value": 20, "evidence": {"posts": 20}}]
    for did in ("did:plc:two", "did:plc:listed", "did:plc:cleared"):
        rows += [{"did": did, "signal": "burst", "value": 15, "evidence": {"posts": 15}},
                 {"did": did, "signal": "account_age", "value": 3, "evidence": {"age_days_at_first_post": 3}}]
    store.save_signals(rows)
    store.save_review({"did": "did:plc:cleared", "reviewer": "gm", "decision": "not_coordinated", "notes": ""})
    flagged = store.analytics().execute("SELECT did FROM flagged ORDER BY 1").fetchall()
    assert flagged == [("did:plc:two",)]
    evidence = store.analytics().execute(
        "SELECT evidence->>'$.posts' FROM signals WHERE did = 'did:plc:one' ORDER BY value").fetchall()
    assert evidence == [("15",), ("20",)]


@pytest.mark.page11
def test_review_queue(store):
    item = {"item_type": "post", "item_id": URI, "topic": "t", "reason": "unsure"}
    store.enqueue_review([item, {"item_type": "account", "item_id": "did:plc:a", "reason": "flagged"}])
    store.enqueue_review([item])                                # already queued: left alone
    assert len(store.pending_reviews()) == 2
    assert [r["item_id"] for r in store.pending_reviews("post", topic="t")] == [URI]
    assert store.pending_reviews("account")[0]["topic"] == ""
    store.resolve_review("post", URI, "t")
    store.resolve_review("account", "did:plc:a")
    assert store.pending_reviews() == []


# --- a store on disk -------------------------------------------------------

@pytest.mark.page05
@pytest.mark.parametrize("backend", ["sqlite", "duckdb"])
def test_a_file_store_can_be_reopened_read_only(tmp_path, backend):
    url = f"{backend}:///{(tmp_path / 'store.db').as_posix()}"
    store = open_store(url)
    store.add_posts([post_row(n) for n in range(30)])
    store.close()

    reader = open_store(url, read_only=True)
    assert len(list(reader.iter_posts())) == 30
    try:
        con = reader.analytics()
    except Exception as e:                                      # the sqlite extension is downloaded on first use
        pytest.skip(f"DuckDB could not attach the {backend} file: {e}")
    assert con.execute("SELECT count(*) FROM posts WHERE created_at >= TIMESTAMPTZ '2026-11-05 00:10:00+00'"
                       ).fetchone()[0] == 20
    assert con.execute("SELECT count(*) FROM labels_final").fetchone()[0] == 0      # the view exists
    con.close()
    reader.close()
