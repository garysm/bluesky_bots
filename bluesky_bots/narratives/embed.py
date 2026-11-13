"""Turn post text into vectors, keeping each vector so no post is embedded twice.

Guide: docs/09-narratives.md (step 1).
"""
from typing import Callable

import numpy as np

from .. import config


def embed(texts: list[str], model: str | None = None, batch: int = 64) -> np.ndarray:
    """One unit-length row per text, from the embedding model named by EMBED_MODEL.

    Sends text only. With a cloud model the text leaves this PC.
    """
    raise NotImplementedError("embed is a task in docs/09-narratives.md.")


def embed_posts(store, posts: list[dict], model: str | None = None,
                embed_fn: Callable[[list[str]], np.ndarray] | None = None) -> np.ndarray:
    """One row per post, in order, taking stored vectors where there are any and embedding the rest.

    posts:    dicts with uri and text
    embed_fn: texts -> vectors; left out, `embed` with this model. A test passes its own.
    New vectors are saved through the store, keyed by uri and model.
    """
    raise NotImplementedError("embed_posts is a task in docs/09-narratives.md.")
