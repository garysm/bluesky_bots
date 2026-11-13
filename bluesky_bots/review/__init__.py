"""Review service: what is waiting for a person, and what they decided.

Two kinds of item: posts no model could label, and accounts with two or more
behavioral signals. Accounts are shown under an anonymous ID with the
evidence. A person's label for a post is stored at the highest tier, so it
wins over every model.

Guide: docs/11-review.md. Command: python -m bluesky_bots.review --help
"""
from .queue import DECISIONS, decide_account, decide_post, pending_accounts, pending_posts, queue_flagged

__all__ = ["DECISIONS", "queue_flagged", "pending_accounts", "decide_account", "pending_posts",
           "decide_post"]
