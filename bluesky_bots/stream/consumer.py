"""Receive events from Jetstream. Knows about websockets and nothing else.

Guide: docs/03-stream.md (steps 1 to 4).
"""
from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable, Iterable
from urllib.parse import urlencode

import websockets

HOST = "wss://jetstream.us-east.bsky.network"
PATH = "/xrpc/network.bsky.jetstream.subscribeEvents"


def build_url(collections: Iterable[str], dids: Iterable[str] = (), cursor: int | None = None) -> str:
    """The full wss:// address for a subscription to these collections (commits only)."""
    raise NotImplementedError("build_url is a task in docs/03-stream.md.")


async def consume(collections: Iterable[str], handle: Callable[[dict], Awaitable[None]],
                  dids: Iterable[str] = (), cursor: int | None = None) -> None:
    """Call handle(event) for every commit, forever; reconnect from the last seq on failure."""
    raise NotImplementedError("consume is a task in docs/03-stream.md.")
