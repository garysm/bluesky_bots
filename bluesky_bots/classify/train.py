"""Train the tier 0 classifier for one dimension of a topic, and choose its threshold.

Guide: docs/08-escalating-labels.md (steps 9 and 10).
"""
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from ..topics import Topic
from .tiers import classifier_path


def training_set(store, topic: Topic, dimension: str, model: str) -> list[dict]:
    """Posts labeled by `model` under the topic's current scheme, as rows of uri, text and value.

    Posts given the dimension's "cannot tell" value are left out.
    """
    raise NotImplementedError("training_set is a task in docs/08-escalating-labels.md.")


def train_classifier(x: np.ndarray, y, test_size: float = 0.25):
    """Fit a logistic regression on vectors `x` and values `y`.

    Returns (classifier, x_test, y_test); the test part was held back and not trained on.
    """
    raise NotImplementedError("train_classifier is a task in docs/08-escalating-labels.md.")


def threshold_table(clf, x_te: np.ndarray, y_te, thresholds=(0.6, 0.7, 0.8, 0.9, 0.95)) -> list[dict]:
    """For each candidate threshold: the share of test posts tier 0 would settle, and its accuracy on them."""
    raise NotImplementedError("threshold_table is a task in docs/08-escalating-labels.md.")


def save_classifier(clf, topic: Topic, dimension: str):
    """Save a trained classifier where the tiered workflow looks for it. Returns the path."""
    raise NotImplementedError("save_classifier is a task in docs/08-escalating-labels.md.")
