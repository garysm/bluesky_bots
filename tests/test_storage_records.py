"""docs/05-storage.md, steps 2 to 4: events into rows, rows into a store."""
import json
from datetime import datetime, timezone

from bluesky_bots.storage import event_to_row, load_events, load_raw_files

from conftest import POST, REPOST, ev

PARENT, ROOT, QUOTED = "at://did:plc:p/x/1", "at://did:plc:r/x/1", "at://did:plc:q/x/1"


def test_a_plain_post():
    table, row = event_to_row(ev("did:plc:a", rkey="9", text="hi", createdAt="2026-11-05T00:00:00Z", langs=["en"]))
    assert table == "posts"
    assert row == {"uri": f"at://did:plc:a/{POST}/9", "did": "did:plc:a",
                   "created_at": datetime(2026, 11, 5, tzinfo=timezone.utc), "text": "hi", "lang": "en",
                   "reply_parent": None, "reply_root": None, "quote_of": None, "source": "jetstream"}


def test_a_reply_that_quotes_with_media():
    _, row = event_to_row(ev("did:plc:a", text="look", createdAt="2026-11-05T00:00:00Z",
                             reply={"parent": {"uri": PARENT}, "root": {"uri": ROOT}},
                             embed={"record": {"record": {"uri": QUOTED}}, "media": {}}))
    assert (row["reply_parent"], row["reply_root"], row["quote_of"]) == (PARENT, ROOT, QUOTED)


def test_a_repost():
    table, row = event_to_row(ev("did:plc:a", REPOST, subject={"uri": PARENT}, createdAt="2026-11-05T00:00:00Z"))
    assert table == "reposts" and row["subject_uri"] == PARENT and set(row) == {"uri", "did", "subject_uri", "created_at"}


def test_missing_and_malformed_fields_become_none():
    _, row = event_to_row(ev("did:plc:a", createdAt="yesterday-ish"))
    assert row["created_at"] is None and row["text"] == "" and row["lang"] is None


def test_load_events_twice_then_delete(mem):
    events = [ev("did:plc:a", rkey="1", text="one", createdAt="2026-11-05T00:00:00Z"),
              ev("did:plc:a", rkey="2", text="reply", createdAt="2026-11-05T00:01:00Z",
                 reply={"parent": {"uri": PARENT}, "root": {"uri": ROOT}}),
              ev("did:plc:a", REPOST, rkey="3", subject={"uri": PARENT}, createdAt="2026-11-05T00:02:00Z")]
    assert load_events(mem, events) == {"posts": 2, "reposts": 1, "deletes": 0}
    load_events(mem, events)
    assert len(list(mem.export_table("posts"))) == 2 and len(list(mem.export_table("reposts"))) == 1

    load_events(mem, [ev("did:plc:a", rkey="1", operation="delete"),
                      ev("did:plc:a", REPOST, rkey="3", operation="delete")])
    assert [p["text"] for p in mem.iter_posts()] == ["reply"]
    assert list(mem.export_table("reposts")) == []


def test_a_post_created_and_deleted_in_one_batch_ends_up_gone(mem):
    load_events(mem, [ev("did:plc:a", rkey="1", text="oops", createdAt="2026-11-05T00:00:00Z"),
                      ev("did:plc:a", rkey="1", operation="delete")])
    assert list(mem.iter_posts()) == []


def test_load_raw_files_leaves_the_newest_and_removes_the_rest(mem, tmp_path):
    for hour, rkey in (("2026-11-12T15", "1"), ("2026-11-12T16", "2"), ("2026-11-12T17", "3")):
        line = json.dumps(ev("did:plc:a", rkey=rkey, text="h" + rkey + " ✓", createdAt="2026-11-12T15:00:00Z"))
        (tmp_path / f"{hour}.jsonl").write_text(line + "\n", encoding="utf-8")
    assert load_raw_files(mem, tmp_path) == 2
    assert sorted(p.name for p in tmp_path.glob("*.jsonl")) == ["2026-11-12T17.jsonl"]
    assert sorted(p["text"] for p in mem.iter_posts()) == ["h1 ✓", "h2 ✓"]
    assert load_raw_files(mem, tmp_path) == 0                    # running it again changes nothing
    assert load_raw_files(mem, tmp_path, keep_newest=False) == 1
    assert list(tmp_path.glob("*.jsonl")) == []
