"""Label a topic's posts with one model.

Guide: docs/07-classify.md (steps 4 to 7).

    START -> load_batch -> classify (once per post) -> check -> persist
                        -> skip                             -> queue_review
"""
from google.adk import Agent, Context, Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import START, Workflow, node
from google.genai import types

from .. import config
from ..topics import Topic
from .scheme import Item, build_instruction, build_label_model, is_unsure, label_rows


def build_workflow(topic: Topic, store, model: str | None = None, labeler=None,
                   max_workers: int = 2) -> Workflow:
    """The labeling workflow for one topic.

    model:   the name recorded with each label and, unless `labeler` is given,
             the model that does the labeling. Defaults to LABEL_MODEL_FAST.
    labeler: what labels one post. Left out, it is an Agent built from the
             topic's scheme. A test passes a plain function (ctx, node_input)
             that returns a label, so no model is called.
    """
    raise NotImplementedError("build_workflow is a task in docs/07-classify.md.")


async def run_workflow(workflow: Workflow, session_id: str, limit: int | None = None,
                       verbose: bool = False) -> str | None:
    """Run a labeling workflow once and return the message from its last node."""
    raise NotImplementedError("run_workflow is a task in docs/07-classify.md.")
