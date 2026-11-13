"""Topic-driven services for collecting, classifying and clustering Bluesky conversations.

Each subpackage is one service; docs/README.md has the map.
"""
from . import config  # noqa: F401  (first, so .env is loaded and settings apply before NumPy is imported)
