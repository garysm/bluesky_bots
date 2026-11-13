"""Label a topic's posts in tiers: a light classifier first, stronger models only for what it leaves.

Guide: docs/08-escalating-labels.md.

    START -> load_batch -> score_classifier -> label_fast -> check_fast -> label_strong -> check_strong -> persist
                        -> skip             -> persist                  -> persist                      -> queue_review
"""
from pathlib import Path

import joblib
from google.adk import Agent, Context
from google.adk.workflow import START, Workflow, node

from .. import config
from ..topics import Topic, entities_in
from .scheme import Item, build_instruction, build_label_model, is_unsure, label_rows


def classifier_path(topic: Topic, dimension: str) -> Path:
    """Where the tier 0 classifier for one dimension of a topic's current scheme is kept."""
    raise NotImplementedError("classifier_path is a task in docs/08-escalating-labels.md.")


def load_classifiers(topic: Topic) -> dict | None:
    """One trained classifier per dimension, or None unless every dimension has one."""
    raise NotImplementedError("load_classifiers is a task in docs/08-escalating-labels.md.")


def build_tiered_workflow(topic: Topic, store, fast: str | None = None, strong: str | None = None,
                          embed_model: str | None = None, threshold: float = 0.9,
                          classifiers: dict | None = None, embed_fn=None,
                          labelers: dict | None = None, max_workers: int = 4) -> Workflow:
    """The tiered labeling workflow for one topic.

    fast, strong: model names for tiers 1 and 2 (LABEL_MODEL_FAST, LABEL_MODEL_STRONG).
    threshold:    tier 0 settles a post only when its least sure dimension reaches this probability.
    classifiers:  {dimension: classifier}; left out, they are loaded from classifier_path.
    embed_fn:     texts -> vectors for tier 0; left out, the narratives service's `embed`.
    labelers:     {"fast": ..., "strong": ...} to stand in for the two agents in a test.
    """
    raise NotImplementedError("build_tiered_workflow is a task in docs/08-escalating-labels.md.")
