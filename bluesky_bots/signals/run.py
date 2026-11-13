"""Compute every signal and save what was observed.

Guide: docs/10-signals.md (step 7).
"""
from .neardup import near_duplicates
from .queries import account_age, behavior_shift, bursts, synchronized_reposts


def compute_signals(store) -> dict[str, int]:
    """Run all five signals over the stored data and save the rows. Returns rows saved per signal."""
    raise NotImplementedError("compute_signals is a task in docs/10-signals.md.")
