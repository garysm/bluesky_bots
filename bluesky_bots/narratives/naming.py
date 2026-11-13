"""Ask a model for a neutral name for a group of posts.

Guide: docs/09-narratives.md (step 5).
"""
import json

from .. import config

NAMING_PROMPT = """Below are posts from one cluster. Give a neutral descriptive name of at
most eight words and a one-sentence summary. Describe the topic, not whether it is right.
Reply as JSON: {"name": "...", "summary": "..."}"""


def name_cluster(sample_posts: list[str], model: str | None = None) -> dict:
    """A {"name", "summary"} dict for a sample of posts, from the model named by NAMING_MODEL.

    Sends text only, never uris or handles.
    """
    raise NotImplementedError("name_cluster is a task in docs/09-narratives.md.")
