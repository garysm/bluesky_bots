"""Shared fixtures. Everything here runs offline: no model, no network, no files outside tmp_path."""
from datetime import datetime, timezone

import pytest

from bluesky_bots.storage import open_store
from bluesky_bots.topics import Topic

POST, REPOST = "app.bsky.feed.post", "app.bsky.feed.repost"
WATCHED = "did:plc:watch"


def make_topic(**changes) -> Topic:
    data = {
        "name": "test-topic",
        "match": {"keywords": ["schumer", "jeffries"], "accounts": [WATCHED]},
        "entities": {"schumer": ["schumer"], "jeffries": ["jeffries"]},
        "labels": {"version": "v1", "instruction": "Test topic.",
                   "dimensions": {"stance": {"values": ["critical", "supportive", "neutral", "unclear"],
                                             "unsure": "unclear"}}},
    }
    data.update(changes)
    return Topic(**data)


@pytest.fixture
def topic() -> Topic:
    return make_topic()


def ev(did, collection=POST, operation="create", rkey="1", **record) -> dict:
    """A made-up Jetstream event."""
    e = {"did": did, "collection": collection, "rkey": rkey, "operation": operation, "seq": 1}
    if operation != "delete":
        e["record"] = record
    return e


def post_row(n: int, did: str = "did:plc:a", text: str = "hello", **changes) -> dict:
    """A made-up `posts` row; n makes the uri and the minute different."""
    row = {"uri": f"at://{did}/{POST}/{n}", "did": did,
           "created_at": datetime(2026, 11, 5, 0, n % 60, tzinfo=timezone.utc), "text": text,
           "lang": "en", "reply_parent": None, "reply_root": None, "quote_of": None, "source": "test"}
    row.update(changes)
    return row


@pytest.fixture(params=["sqlite", "duckdb"])
def store(request):
    """An empty in-memory store, once per backend. Used by the contract tests."""
    s = open_store(f"{request.param}://:memory:")
    yield s
    s.close()


@pytest.fixture
def mem():
    """An empty in-memory SQLite store, for tests of the other services."""
    s = open_store("sqlite://:memory:")
    yield s
    s.close()
