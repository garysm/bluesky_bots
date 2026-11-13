"""Group similar posts into narratives and keep the same ID from run to run.

Guide: docs/09-narratives.md (steps 2 to 4). Everything here is arithmetic on
vectors; nothing touches a model or the database.
"""
import numpy as np
from sklearn.cluster import HDBSCAN


def cluster(x: np.ndarray, min_size: int = 25) -> np.ndarray:
    """One integer label per row of x. -1 means the post belongs to no narrative."""
    raise NotImplementedError("cluster is a task in docs/09-narratives.md.")


def centroids(x: np.ndarray, labels: np.ndarray) -> dict[int, np.ndarray]:
    """Each cluster number mapped to its centroid, scaled to unit length. Leaves out -1."""
    raise NotImplementedError("centroids is a task in docs/09-narratives.md.")


def match_to_previous(today: dict, previous: dict, threshold: float = 0.8) -> dict:
    """Map each of today's cluster numbers to a previous narrative id, or None for a new narrative.

    Both arguments map a number to a unit-length centroid.
    """
    raise NotImplementedError("match_to_previous is a task in docs/09-narratives.md.")


def assign_ids(mapping: dict, next_id: int) -> dict[int, int]:
    """Give every cluster a narrative id: the previous id it matched, or a new one from next_id up.

    If two clusters matched the same previous narrative, the first keeps the
    id and the other gets a new one, so an id never names two groups in one run.
    """
    raise NotImplementedError("assign_ids is a task in docs/09-narratives.md.")


def typical(x: np.ndarray, labels: np.ndarray, k: int, centroid: np.ndarray, n: int = 15) -> list[int]:
    """Row numbers of the n posts in cluster k closest to its centroid, closest first."""
    raise NotImplementedError("typical is a task in docs/09-narratives.md.")
