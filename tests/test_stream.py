"""docs/03-stream.md. Only the parts that need no connection."""
import asyncio
import json
from datetime import datetime, timezone

from bluesky_bots.stream import build_url, hour_file, load_cursor, make_handler, save_cursor

from conftest import ev


def test_build_url():
    assert build_url(["app.bsky.feed.post", "app.bsky.feed.repost"]) == (
        "wss://jetstream.us-east.bsky.network/xrpc/network.bsky.jetstream.subscribeEvents"
        "?collections=app.bsky.feed.post&collections=app.bsky.feed.repost&kinds=commit")


def test_build_url_with_cursor():
    assert build_url(["app.bsky.feed.post"], cursor=42).endswith("&kinds=commit&cursor=42")


def test_hour_file_is_named_for_the_utc_hour(tmp_path):
    now = datetime(2026, 11, 12, 16, 59, 59, tzinfo=timezone.utc)
    assert hour_file(tmp_path, now).name == "2026-11-12T16.jsonl"


def test_handler_keeps_only_what_keep_accepts(tmp_path):
    state = {}
    handle = make_handler(lambda e: "keep" in e["record"]["text"], tmp_path / "raw", state)
    asyncio.run(handle({**ev("did:plc:a", text="keep me ✓"), "seq": 7}))
    asyncio.run(handle({**ev("did:plc:a", text="drop me"), "seq": 8}))
    files = list((tmp_path / "raw").glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["record"]["text"] for line in lines] == ["keep me ✓"]
    assert state["cursor"] == 8                 # the last event received, not the last one kept


def test_cursor_is_saved_and_read_back(tmp_path):
    path = tmp_path / "state" / "cursor.json"
    assert load_cursor(path) is None
    save_cursor(path, 123)
    save_cursor(path, 456)
    assert load_cursor(path) == 456
    assert not path.with_suffix(".tmp").exists()
