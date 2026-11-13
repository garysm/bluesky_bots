"""Project settings, read once from .env in the project root.

Every service imports its paths and names from here, so nothing else reads
the environment or builds a path by hand.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# On this PC, NumPy's threaded math library (MKL) crashes Python outright on
# any sizeable matrix operation; its single-threaded mode works. The setting
# only takes effect if it is made before NumPy is first imported, which is why
# it lives here and why `import bluesky_bots` should come first in a notebook.
# A value in .env or the shell wins. See "Good to know" in docs/01-setup.md.
os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")


def _path(key: str, default: str) -> Path:
    """A path from .env; relative paths are taken from the project root."""
    p = Path(os.environ.get(key, default))
    return p if p.is_absolute() else ROOT / p


DATA_DIR = _path("DATA_DIR", "data")
RAW_DIR = DATA_DIR / "raw"          # hourly landing files written by the stream
STATE_DIR = DATA_DIR / "state"      # stream cursor, resolved handles
MODELS_DIR = DATA_DIR / "models"    # trained first-tier classifiers
TOPICS_DIR = _path("TOPICS_DIR", "topics")
OUT_DIR = _path("OUT_DIR", "out")

# Which storage backend to use, and where. See docs/17-choosing-storage.md.
STORAGE_URL = os.environ.get(
    "STORAGE_URL", "duckdb:///" + (DATA_DIR / "narrative.duckdb").as_posix())


def model(key: str) -> str:
    """The model name stored under `key` in .env, for example model("LABEL_MODEL_FAST")."""
    try:
        return os.environ[key]
    except KeyError:
        raise RuntimeError(f"{key} is not set in .env; see docs/16-choosing-models.md") from None
