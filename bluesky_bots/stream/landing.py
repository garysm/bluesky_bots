"""Write kept events to hourly landing files, and remember how far the stream got.

Guide: docs/03-stream.md (steps 5 to 7).
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable


def hour_file(raw_dir: str | Path, now: datetime | None = None) -> Path:
    """The landing file for the current hour in UTC, for example data/raw/2026-11-12T16.jsonl."""
    raise NotImplementedError("hour_file is a task in docs/03-stream.md.")


def make_handler(keep: Callable[[dict], bool], raw_dir: str | Path,
                 state: dict | None = None) -> Callable[[dict], Awaitable[None]]:
    """The coroutine `consume` calls for each event.

    It appends the events that `keep` accepts to the current hour's file, one
    JSON object per line. If `state` is given, it records the seq of every
    event received (kept or not) under state["cursor"].
    """
    raise NotImplementedError("make_handler is a task in docs/03-stream.md.")


def save_cursor(path: str | Path, seq: int) -> None:
    """Save the stream position so that a crash half-way through cannot leave a broken file."""
    raise NotImplementedError("save_cursor is a task in docs/03-stream.md.")


def load_cursor(path: str | Path) -> int | None:
    """The saved stream position, or None if there is none yet."""
    raise NotImplementedError("load_cursor is a task in docs/03-stream.md.")


async def every(seconds: float, fn: Callable[[], None]) -> None:
    """Call fn() every few seconds, forever. Run it as a task beside the consumer."""
    raise NotImplementedError("every is a task in docs/03-stream.md.")
