"""One clustering run for a topic: embed, cluster, carry IDs forward, name, save.

Guide: docs/09-narratives.md (step 6).
"""
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable

import numpy as np

from .. import config
from ..topics import Topic
from .cluster import assign_ids, centroids, cluster, match_to_previous, typical
from .embed import embed_posts
from .naming import name_cluster

MIN_CHARS = 40      # shorter posts group by phrasing, not by topic


def previous_centroids(store, topic: Topic, model: str, before: date) -> tuple[dict, dict]:
    """The centroids and names of the latest run before `before`.

    Returns ({narrative_id: centroid}, {narrative_id: {"name", "summary"}}),
    both empty when there is no earlier run. The centroids are worked out
    again from the stored vectors of the posts in each narrative.
    """
    raise NotImplementedError("previous_centroids is a task in docs/09-narratives.md.")


def run_topic(store, topic: Topic, today: date | None = None, days: int = 7, model: str | None = None,
              embed_fn: Callable | None = None, namer: Callable[[list[str]], dict] | None = None) -> dict:
    """Cluster the last `days` days of a topic's posts and save the run under `today`.

    A narrative that continues from the previous run keeps its id and its
    name. Returns {"posts", "narratives", "unclustered"}.
    """
    raise NotImplementedError("run_topic is a task in docs/09-narratives.md.")
