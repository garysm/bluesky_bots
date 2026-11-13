"""Signals service: behavioral flags from timing, account age and repeated text.

No model is involved and no label is ever read: what an account says has no
part in whether it is flagged. No signal is proof of anything; an account
reaches the review queue only when two different signals fire.

Guide: docs/10-signals.md. Command: python -m bluesky_bots.signals
"""
from .neardup import near_duplicate_groups, near_duplicates, normalize
from .queries import account_age, behavior_shift, bursts, synchronized_reposts
from .run import compute_signals

__all__ = ["account_age", "bursts", "synchronized_reposts", "behavior_shift", "normalize",
           "near_duplicate_groups", "near_duplicates", "compute_signals"]
