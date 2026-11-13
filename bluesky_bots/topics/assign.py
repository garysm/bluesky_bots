"""Record which stored posts belong to a topic.

Guide: docs/02-topics.md (step 7).
"""
from __future__ import annotations

from ..aturi import did_of
from .match import match_post
from .schema import Topic


def assign(store, topic: Topic) -> int:
    """Work out which stored posts are in the topic and save that as its membership.

    Replaces the topic's earlier membership, so it is safe to run again after
    the topic file changes. Returns how many posts are in the topic.
    """
    raise NotImplementedError("assign is a task in docs/02-topics.md.")
