"""Fetch history from the Bluesky AppView: an account's posts, search results, profiles.

Guide: docs/04-backfill.md. No function here names a subject; the command in
__main__.py feeds them a topic's searches and accounts.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator

import httpx

from ..aturi import quoted_uri

APPVIEW = "https://api.bsky.app/xrpc"


def paged(client: httpx.Client, method: str, params: dict, key: str, max_pages: int = 500,
          sleep: Callable[[float], None] = time.sleep) -> Iterator[dict]:
    """Yield every item under `key` from an endpoint that pages with a cursor.

    Waits and asks again on a 429. `sleep` is a parameter so a test can pass
    one that does not wait.
    """
    raise NotImplementedError("paged is a task in docs/04-backfill.md.")


def parse_ts(value: str) -> datetime:
    """A timezone-aware datetime from an ISO string; a value with no zone is taken to be UTC."""
    raise NotImplementedError("parse_ts is a task in docs/04-backfill.md.")


def sort_time(post: dict) -> datetime:
    """The one timestamp to trust for an AppView post: the earlier of indexedAt and createdAt.

    Falls back to indexedAt when createdAt is missing or is not a date.
    """
    raise NotImplementedError("sort_time is a task in docs/04-backfill.md.")


def author_history(client: httpx.Client, actor: str, start: datetime) -> Iterator[dict]:
    """Feed items (posts and reposts) by one account, newest first, back to `start`."""
    raise NotImplementedError("author_history is a task in docs/04-backfill.md.")


def search_posts(client: httpx.Client, query: str, start: datetime, end: datetime,
                 sleep: Callable[[float], None] = time.sleep) -> Iterator[dict]:
    """Every post search can find for `query` between `start` and `end`, each yielded once.

    Walks backwards from `end` by moving `until`, never sending a cursor.
    Prints how many posts it found for each day when it finishes.
    """
    raise NotImplementedError("search_posts is a task in docs/04-backfill.md.")


def post_to_row(post: dict, source: str) -> dict:
    """A `posts` table row from an AppView post (a search result, or the "post" of a feed item).

    `source` says where it came from, for example 'backfill_search' or 'backfill_feed'.
    """
    raise NotImplementedError("post_to_row is a task in docs/04-backfill.md.")


def resolve_did(client: httpx.Client, handle: str) -> str:
    """The DID of the account with this handle."""
    raise NotImplementedError("resolve_did is a task in docs/04-backfill.md.")


def account_created(client: httpx.Client, did: str) -> str | None:
    """When an account was created, as an ISO string, from the PLC directory or the profile."""
    raise NotImplementedError("account_created is a task in docs/04-backfill.md.")
