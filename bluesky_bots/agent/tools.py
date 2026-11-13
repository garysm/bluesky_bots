"""The functions the analyst agent may call. They return aggregates only.

Guide: docs/12-agent.md (steps 1 and 2). A model sees each function's name,
type hints and docstring, so those are written for the model. No tool returns
a row about an individual account, so the agent cannot repeat a handle or a
DID it never receives.
"""
from contextlib import contextmanager

from ..storage import open_store
from ..topics import get_topic, load_topics


@contextmanager
def _session():
    """A read-only analysis connection, closed afterwards. A test replaces this."""
    store = open_store(read_only=True)
    con = store.analytics()
    try:
        yield con
    finally:
        con.close()
        store.close()


def _dicts(cur) -> list[dict]:
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def list_topics() -> list[dict]:
    """The topics that can be asked about. For each: its name, title, the entities
    a label can be about, and each label dimension with its allowed values.
    Call this first to learn the exact names the other tools take."""
    raise NotImplementedError("list_topics is a task in docs/12-agent.md.")


def label_counts_by_day(topic: str, dimension: str, start: str, end: str, entity: str = "") -> list[dict]:
    """Daily counts of a topic's posts for each value of one label dimension.
    Each row has day, value, n_all (posts from all accounts) and n_unflagged
    (posts from accounts with no behavioral flags). Dates are YYYY-MM-DD and
    both are included. Pass entity to count only labels about that entity."""
    raise NotImplementedError("label_counts_by_day is a task in docs/12-agent.md.")


def narrative_share(topic: str, run_date: str = "", top_n: int = 10) -> list[dict]:
    """The largest narratives in a topic with their share of the topic's clustered
    posts, as name, n_posts and share_pct. run_date is YYYY-MM-DD; leave it
    empty for the latest clustering run."""
    raise NotImplementedError("narrative_share is a task in docs/12-agent.md.")
