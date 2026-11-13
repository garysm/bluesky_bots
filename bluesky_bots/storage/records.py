"""Turn Jetstream events into table rows and feed them to a store.

Guide: docs/05-storage.md (steps 2 to 4). Nothing here depends on which
backend the store is.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..aturi import at_uri, quoted_uri
from .base import to_utc

REPOST = "app.bsky.feed.repost"


def event_to_row(event: dict) -> tuple[str, dict]:
    """Flatten a Jetstream create or update event into ("posts" or "reposts", row).

    A field the record does not have becomes None in the row.
    """
    raise NotImplementedError("event_to_row is a task in docs/05-storage.md.")


def load_events(store, events: Iterable[dict], batch: int = 500) -> dict[str, int]:
    """Store Jetstream events, and remove what a delete event names.

    Events are applied in order, so a post created and then deleted in the
    same file ends up gone. Returns how many posts, reposts and deletes it saw.
    """
    raise NotImplementedError("load_events is a task in docs/05-storage.md.")


def load_raw_files(store, raw_dir: str | Path, keep_newest: bool = True) -> int:
    """Feed the stream's hourly files through load_events, removing each file once it is stored.

    The newest file is left alone when keep_newest is true, because the
    stream is still appending to it. Returns how many files were loaded.
    """
    raise NotImplementedError("load_raw_files is a task in docs/05-storage.md.")
