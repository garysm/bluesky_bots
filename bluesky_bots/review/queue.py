"""What is waiting for a person, and what they decided.

Guide: docs/11-review.md. An account is always shown under its anonymous ID
with the evidence, never its handle or DID: a behavioral call does not need
to know who the person is.
"""
import json

from ..privacy import anon_id
from ..storage import HUMAN_TIER
from ..topics import Topic

DECISIONS = ("coordinated", "not_coordinated", "undecided")


def queue_flagged(store) -> int:
    """Put every account in the `flagged` view on the review queue. Returns how many are flagged."""
    raise NotImplementedError("queue_flagged is a task in docs/11-review.md.")


def pending_accounts(store) -> list[dict]:
    """Queued accounts as a reviewer should see them: an anonymous ID and the evidence rows."""
    raise NotImplementedError("pending_accounts is a task in docs/11-review.md.")


def decide_account(store, account: str, reviewer: str, decision: str, notes: str = "") -> None:
    """Record a reviewer's decision about a queued account, named by its anonymous ID."""
    raise NotImplementedError("decide_account is a task in docs/11-review.md.")


def pending_posts(store, topic: Topic) -> list[dict]:
    """Queued posts of a topic with their text and the label the models settled on.

    Each item carries its uri so a decision can be recorded; do not show it
    to the reviewer, because it contains the author's DID.
    """
    raise NotImplementedError("pending_posts is a task in docs/11-review.md.")


def decide_post(store, topic: Topic, uri: str, reviewer: str, values: dict[str, str],
                target: str = "") -> None:
    """Record a person's label for a queued post and take it off the queue.

    values maps a dimension to the value the reviewer chose. The label is
    stored with model 'human:<reviewer>' at the highest tier, so labels_final
    prefers it to any model's answer.
    """
    raise NotImplementedError("decide_post is a task in docs/11-review.md.")
