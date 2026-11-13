"""Agent service: an analyst agent that drafts findings from aggregate numbers.

Its tools are the boundary of what it can know. They return counts per day
and per narrative, never a row about an individual account.

Guide: docs/12-agent.md. Command: python -m bluesky_bots.agent "your request"
"""
from .analyst import INSTRUCTION, build_analyst
from .tools import label_counts_by_day, list_topics, narrative_share

__all__ = ["INSTRUCTION", "build_analyst", "list_topics", "label_counts_by_day", "narrative_share"]
