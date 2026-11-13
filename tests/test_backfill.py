"""docs/04-backfill.md. The AppView is replaced by a fake transport, so nothing leaves this PC."""
from datetime import datetime, timezone

import httpx
import pytest

from bluesky_bots.backfill import paged, post_to_row, sort_time

INDEXED = "2026-11-05T00:00:10.000Z"


@pytest.mark.parametrize("created,expected", [
    ("2026-11-05T00:00:00.000Z", datetime(2026, 11, 5, 0, 0, 0, tzinfo=timezone.utc)),   # the earlier one
    ("2030-01-01T00:00:00.000Z", datetime(2026, 11, 5, 0, 0, 10, tzinfo=timezone.utc)),  # a future date loses
    ("not a date", datetime(2026, 11, 5, 0, 0, 10, tzinfo=timezone.utc)),
    ("2026-11-05T00:00:00", datetime(2026, 11, 5, 0, 0, 0, tzinfo=timezone.utc)),        # no zone means UTC
])
def test_sort_time(created, expected):
    got = sort_time({"indexedAt": INDEXED, "record": {"createdAt": created}})
    assert got == expected and got.tzinfo is not None


def test_sort_time_without_created_at():
    assert sort_time({"indexedAt": INDEXED, "record": {}}).second == 10


def test_paged_follows_the_cursor_and_retries_after_429():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        if len(calls) == 2:
            return httpx.Response(429)
        cursor = request.url.params.get("cursor")
        if cursor is None:
            return httpx.Response(200, json={"feed": [1, 2], "cursor": "a"})
        if cursor == "a":
            return httpx.Response(200, json={"feed": [3], "cursor": "b"})
        return httpx.Response(200, json={"feed": [4]})

    waits = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        params = {"actor": "x", "limit": 100}
        items = list(paged(client, "app.bsky.feed.getAuthorFeed", params, "feed", sleep=waits.append))
    assert items == [1, 2, 3, 4]
    assert params == {"actor": "x", "limit": 100}       # the caller's dict is not changed
    assert 30 in waits                                  # it waited after the 429
    assert [c.get("cursor") for c in calls] == [None, "a", "a", "b"]


def test_paged_stops_at_max_pages():
    def handler(request):
        return httpx.Response(200, json={"feed": [1], "cursor": "more"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert len(list(paged(client, "m", {}, "feed", max_pages=3, sleep=lambda s: None))) == 3


def test_paged_raises_on_other_errors():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as client:
        with pytest.raises(httpx.HTTPStatusError):
            list(paged(client, "m", {}, "feed", sleep=lambda s: None))


def test_post_to_row():
    post = {"uri": "at://did:plc:a/app.bsky.feed.post/1", "author": {"did": "did:plc:a"},
            "indexedAt": INDEXED,
            "record": {"text": "hi", "createdAt": "2026-11-05T00:00:00.000Z", "langs": ["en", "fr"],
                       "reply": {"parent": {"uri": "at://p"}, "root": {"uri": "at://r"}},
                       "embed": {"record": {"uri": "at://q"}}}}
    row = post_to_row(post, "backfill_search")
    assert row == {"uri": post["uri"], "did": "did:plc:a",
                   "created_at": datetime(2026, 11, 5, tzinfo=timezone.utc), "text": "hi", "lang": "en",
                   "reply_parent": "at://p", "reply_root": "at://r", "quote_of": "at://q",
                   "source": "backfill_search"}
    bare = post_to_row({**post, "record": {}}, "backfill_feed")
    assert bare["text"] == "" and bare["lang"] is None and bare["reply_parent"] is None
