"""Narratives service: embed a topic's posts, group similar ones, name the groups,
and keep the same narrative ID from one run to the next.

Guide: docs/09-narratives.md. Command: python -m bluesky_bots.narratives --help
"""
from .cluster import assign_ids, centroids, cluster, match_to_previous, typical
from .embed import embed, embed_posts
from .naming import NAMING_PROMPT, name_cluster
from .run import previous_centroids, run_topic

__all__ = ["embed", "embed_posts", "cluster", "centroids", "match_to_previous", "assign_ids",
           "typical", "NAMING_PROMPT", "name_cluster", "previous_centroids", "run_topic"]
