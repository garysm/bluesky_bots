"""Decide whether a post belongs to a topic.

Guide: docs/02-topics.md. Nothing here touches the network or the database.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Callable, Iterable

from ..aturi import did_of, quoted_uri
from .schema import Topic

REPOST = "app.bsky.feed.repost"


@lru_cache(maxsize=None)
def keyword_regex(keywords: tuple[str, ...], patterns: tuple[str, ...] = ()) -> re.Pattern | None:
    """One compiled, case-insensitive pattern for a topic's keywords and patterns.

    Each keyword matches only as a whole word or phrase. Returns None when
    there is nothing to match. Arguments are tuples so the result can be cached.
    """
    raise NotImplementedError("keyword_regex is a task in docs/02-topics.md.")


def match_text(topic: Topic, text: str) -> bool:
    """True when the text contains one of the topic's keywords or matches one of its patterns."""
    raise NotImplementedError("match_text is a task in docs/02-topics.md.")


def match_post(topic: Topic, did: str, text: str = "", linked: Iterable[str] = ()) -> str | None:
    """Which rule puts a post in the topic: 'account', 'keyword', 'linked', or None for no match.

    did:    the author
    text:   the post's text ('' for a repost)
    linked: DIDs of the accounts whose posts this one replies to, quotes or reposts
    """
    raise NotImplementedError("match_post is a task in docs/02-topics.md.")


def event_fields(event: dict) -> dict:
    """The did, text and linked DIDs of a Jetstream create or update event, as match_post takes them."""
    raise NotImplementedError("event_fields is a task in docs/02-topics.md.")


def match_event(topic: Topic, event: dict) -> str | None:
    """Which rule puts a Jetstream event in the topic, or None."""
    raise NotImplementedError("match_event is a task in docs/02-topics.md.")


def capture_filter(topics: Iterable[Topic]) -> Callable[[dict], bool]:
    """The stream's default `keep` function: keep an event if any of these topics matches it.

    Deletes are always kept. A delete does not say what the post was, so the
    only way to honor it is to pass it on and let storage remove the post if
    it is there.
    """
    raise NotImplementedError("capture_filter is a task in docs/02-topics.md.")


def entities_in(topic: Topic, text: str) -> list[str]:
    """The topic's entities whose keywords appear in the text."""
    raise NotImplementedError("entities_in is a task in docs/02-topics.md.")
