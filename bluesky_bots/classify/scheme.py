"""Turn a topic's label scheme into what a model is asked for and what gets stored.

Guide: docs/07-classify.md (steps 1 to 3).
"""
from typing import Literal

from pydantic import BaseModel, create_model

from ..topics import Topic

# Sent to the model before every topic's own instruction, so a topic file
# cannot leave these rules out. See docs/14-guardrails.md.
BASE_INSTRUCTION = """You label one Bluesky post.
Label only what the post says. Do not guess whether the author is sincere,
automated, or part of a campaign; that is not your job and you lack the evidence.
Every allowed value is equally ordinary. Apply the same care to each of them.
When sarcasm or missing context makes an answer uncertain, give the "cannot tell" value named below.
Copy i unchanged."""


class Item(BaseModel):
    """What a model sees of a post: a position number and text. No uri, so no DID leaves this PC."""
    i: int
    text: str
    parent_text: str | None = None


def build_label_model(topic: Topic) -> type[BaseModel]:
    """The Pydantic model a labeler must answer with, built from the topic's label scheme.

    Fields: `i` (the position number, copied back), `entities` (which of the
    topic's entities the post is about; only when the topic has entities),
    and one field per dimension, restricted to that dimension's values.
    """
    raise NotImplementedError("build_label_model is a task in docs/07-classify.md.")


def build_instruction(topic: Topic) -> str:
    """The full instruction for a labeler: the base rules, the topic's wording, then the allowed answers."""
    raise NotImplementedError("build_instruction is a task in docs/07-classify.md.")


def is_unsure(topic: Topic, label: dict) -> bool:
    """True when any dimension of a label holds that dimension's "cannot tell" value."""
    raise NotImplementedError("is_unsure is a task in docs/07-classify.md.")


def label_rows(topic: Topic, uri: str, label: dict, model: str, tier: int,
               confidence: float | None = None) -> list[dict]:
    """The `labels` table rows for one post's label: one row per target and dimension.

    The targets are the entities the label names, or '' (the post as a
    whole) when it names none.
    """
    raise NotImplementedError("label_rows is a task in docs/07-classify.md.")
