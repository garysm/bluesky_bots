"""Find almost-identical text posted by many accounts.

Guide: docs/10-signals.md (step 5).
"""
import re
from typing import Iterable

from datasketch import MinHash, MinHashLSH


def normalize(text: str) -> str:
    """Text with case, links, mentions and runs of spaces removed, so trivial differences disappear."""
    raise NotImplementedError("normalize is a task in docs/10-signals.md.")


def near_duplicate_groups(rows: Iterable[tuple], threshold: float = 0.8, min_accounts: int = 5,
                          min_chars: int = 40) -> list[set[str]]:
    """Groups of post uris with near-identical text, each spanning at least `min_accounts` accounts.

    rows: an iterable of (uri, did, text).
    """
    raise NotImplementedError("near_duplicate_groups is a task in docs/10-signals.md.")


def near_duplicates(rows: Iterable[tuple], **settings) -> list[dict]:
    """Signal rows, one per account in a near-duplicate group.

    The evidence holds the shared text and the counts, not a list of accounts.
    """
    raise NotImplementedError("near_duplicates is a task in docs/10-signals.md.")
