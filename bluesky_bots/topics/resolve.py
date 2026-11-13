"""Turn the handles in topic files into DIDs, remembering the answers.

Matching works on DIDs, because a handle can change and a DID cannot. A topic
file may list either. Entries that are already DIDs need nothing; handles are
looked up once and cached in a small JSON file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

from .. import config
from .schema import Topic


def resolve_accounts(topics: Iterable[Topic], resolve: Callable[[str], str],
                     cache_path: str | Path | None = None) -> None:
    """Fill in `topic.dids` for every account written as a handle.

    resolve(handle) returns the DID; `resolve_did` from the backfill service,
    bound to an HTTP client, is the usual one.
    """
    cache_path = Path(cache_path or config.STATE_DIR / "dids.json")
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    changed = False
    for topic in topics:
        for handle in topic.handles:
            if handle not in cache:
                cache[handle] = resolve(handle)
                changed = True
            topic.dids.add(cache[handle])
    if changed:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
