"""Behavioral signals from timing and account age. No model, and no label is ever read.

Guide: docs/10-signals.md (steps 1 to 4). Each function runs one query on a
DuckDB connection from `store.analytics()` and returns rows ready for
`store.save_signals`: did, signal, value, evidence, and where it applies
window_start. Evidence says what was observed, never a verdict.
"""
from datetime import date


def _dicts(cur) -> list[dict]:
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def account_age(con, max_days: int = 30) -> list[dict]:
    """Accounts that were under `max_days` old when they first posted in the stored data."""
    raise NotImplementedError("account_age is a task in docs/10-signals.md.")


def bursts(con, minutes: int = 10, min_posts: int = 15) -> list[dict]:
    """Accounts that made `min_posts` or more posts inside one window of `minutes`."""
    raise NotImplementedError("bursts is a task in docs/10-signals.md.")


def synchronized_reposts(con, seconds: int = 60, min_together: int = 5) -> list[dict]:
    """Accounts in a pair that reposted the same posts within `seconds` of each other, repeatedly.

    One row per account. The evidence counts partners; it does not name them.
    """
    raise NotImplementedError("synchronized_reposts is a task in docs/10-signals.md.")


def behavior_shift(con, min_z: float = 4, today: date | None = None) -> list[dict]:
    """Accounts posting far more in the last 7 days than their own 60 days before that.

    The measure is a z-score against the account's own baseline; accounts
    with fewer than 20 active days in the baseline are left out.
    """
    raise NotImplementedError("behavior_shift is a task in docs/10-signals.md.")
