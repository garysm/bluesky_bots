"""An agent that drafts findings from the numbers its tools return.

Guide: docs/12-agent.md (steps 3 and 4).
"""
from google.adk import Agent

from .. import config
from .tools import label_counts_by_day, list_topics, narrative_share

INSTRUCTION = """You draft findings for a research report about conversations on Bluesky.
Use only numbers returned by your tools and quote them exactly. Call list_topics
first to learn the topic names, dimensions and values. Describe what was observed;
do not call anything a campaign, a bot network or inauthentic. Say plainly when the
flagged and unflagged series are close. Never mention individual accounts.
A human will edit your draft."""


def build_analyst(model: str | None = None) -> Agent:
    """The analyst agent: ANALYST_MODEL (or `model`), the instruction above, and the three tools."""
    raise NotImplementedError("build_analyst is a task in docs/12-agent.md.")
