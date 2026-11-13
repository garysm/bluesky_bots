"""The default storage backend: one DuckDB file.

Guide: docs/05-storage.md builds this class step by step, and later service
pages add the methods their service needs. `sqlite_store.py` is a finished
backend to compare against. This one is done when
tests/test_store_contract.py passes for "duckdb".

DuckDB has real timestamp, boolean, date and list types, so there is less
converting to do here than in the SQLite backend.
"""
from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path
from typing import Iterable, Iterator

import duckdb
import numpy as np

from .. import config
from . import views
from .base import TABLES, URI_TABLES, create_tables_sql, now_utc, to_date, to_utc


def _encode(kind: str, value):
    """A Python value in the form DuckDB takes for a column of this kind."""
    raise NotImplementedError("_encode is a task in docs/05-storage.md.")


def _decode(kind: str, value):
    """A value DuckDB returned, in the form the Store interface promises."""
    raise NotImplementedError("_decode is a task in docs/05-storage.md.")


class DuckDBStore:
    dialect = "duckdb"

    def __init__(self, path: str, read_only: bool = False):
        """Open the database file (or ':memory:'), creating its folder when opening for writing."""
        raise NotImplementedError("DuckDBStore.__init__ is a task in docs/05-storage.md. Until it is written, put STORAGE_URL=sqlite:///data/narrative.sqlite in .env to use the finished SQLite backend.")

    def init_schema(self) -> None:
        """Create the tables and the analysis views if they are missing."""
        raise NotImplementedError("DuckDBStore.init_schema is a task in docs/05-storage.md.")

    def close(self) -> None:
        """Close the connection."""
        raise NotImplementedError("DuckDBStore.close is a task in docs/05-storage.md.")

    # --- helpers ----------------------------------------------------------
    def _insert(self, table: str, rows: Iterable[dict], on_conflict: str = "DO NOTHING") -> None:
        """Insert rows into a table in one transaction; columns a row leaves out are stored as NULL."""
        raise NotImplementedError("DuckDBStore._insert is a task in docs/05-storage.md.")

    def _rows(self, table: str, sql: str, params=()) -> list[dict]:
        """Run a query and return dicts, decoding each column by its type in `table`."""
        raise NotImplementedError("DuckDBStore._rows is a task in docs/05-storage.md.")

    # --- ingest -----------------------------------------------------------
    def add_posts(self, rows: Iterable[dict]) -> None:
        """Insert posts. A row whose uri is already stored is skipped."""
        raise NotImplementedError("DuckDBStore.add_posts is a task in docs/05-storage.md.")

    def add_reposts(self, rows: Iterable[dict]) -> None:
        """Insert reposts. A row whose uri is already stored is skipped."""
        raise NotImplementedError("DuckDBStore.add_reposts is a task in docs/05-storage.md.")

    def upsert_accounts(self, rows: Iterable[dict]) -> None:
        """Create accounts or update them. A column that is missing or None keeps its stored value."""
        raise NotImplementedError("DuckDBStore.upsert_accounts is a task in docs/05-storage.md.")

    def delete_record(self, uri: str) -> None:
        """Remove a record its author deleted from every table in URI_TABLES and from the review queue."""
        raise NotImplementedError("DuckDBStore.delete_record is a task in docs/05-storage.md.")

    # --- fetch ------------------------------------------------------------
    def iter_posts(self) -> Iterator[dict]:
        """Every stored post."""
        raise NotImplementedError("DuckDBStore.iter_posts is a task in docs/05-storage.md.")

    def _topic_posts(self, topic: str, extra: str = "", params: list | None = None,
                     limit: int | None = None) -> list[dict]:
        """A topic's posts with parent_text, oldest first; `extra` adds conditions to the WHERE."""
        raise NotImplementedError("DuckDBStore._topic_posts is a task in docs/05-storage.md.")

    def posts_in_topic(self, topic, since=None, until=None) -> list[dict]:
        """Posts assigned to a topic, oldest first, each with `parent_text`."""
        raise NotImplementedError("DuckDBStore.posts_in_topic is a task in docs/05-storage.md.")

    def unlabeled_posts(self, topic, scheme_version, model=None, limit=None) -> list[dict]:
        """Posts in a topic with no label under this scheme version (from `model`, or from any model)."""
        raise NotImplementedError("DuckDBStore.unlabeled_posts is a task in docs/07-classify.md.")

    # --- derived data -----------------------------------------------------
    def set_post_topics(self, topic: str, rows: Iterable[dict]) -> None:
        """Replace a topic's membership with `rows` (each has uri and matched_by)."""
        raise NotImplementedError("DuckDBStore.set_post_topics is a task in docs/05-storage.md.")

    def save_labels(self, rows: Iterable[dict]) -> None:
        """Store label rows. A row with the same key replaces the old one."""
        raise NotImplementedError("DuckDBStore.save_labels is a task in docs/07-classify.md.")

    def save_vectors(self, model: str, vectors: dict[str, np.ndarray]) -> None:
        """Store one vector per uri for an embedding model."""
        raise NotImplementedError("DuckDBStore.save_vectors is a task in docs/09-narratives.md.")

    def load_vectors(self, model: str, uris=None) -> dict[str, np.ndarray]:
        """The stored vectors for these uris (or all of them), keyed by uri."""
        raise NotImplementedError("DuckDBStore.load_vectors is a task in docs/09-narratives.md.")

    def save_narratives(self, topic, run_date, narratives, assignments) -> None:
        """Replace one clustering run for a topic and date."""
        raise NotImplementedError("DuckDBStore.save_narratives is a task in docs/09-narratives.md.")

    def narrative_run(self, topic, before=None) -> dict | None:
        """The latest clustering run for a topic (earlier than `before`, if given), or None."""
        raise NotImplementedError("DuckDBStore.narrative_run is a task in docs/09-narratives.md.")

    def save_signals(self, rows: Iterable[dict]) -> None:
        """Append signal rows."""
        raise NotImplementedError("DuckDBStore.save_signals is a task in docs/10-signals.md.")

    def enqueue_review(self, rows: Iterable[dict]) -> None:
        """Add items for a person to look at. An item already queued is left alone."""
        raise NotImplementedError("DuckDBStore.enqueue_review is a task in docs/11-review.md.")

    def pending_reviews(self, item_type=None, topic=None) -> list[dict]:
        """Queued items, oldest first."""
        raise NotImplementedError("DuckDBStore.pending_reviews is a task in docs/11-review.md.")

    def resolve_review(self, item_type: str, item_id: str, topic: str = "") -> None:
        """Take an item off the queue."""
        raise NotImplementedError("DuckDBStore.resolve_review is a task in docs/11-review.md.")

    def save_review(self, row: dict) -> None:
        """Record a reviewer's decision about an account."""
        raise NotImplementedError("DuckDBStore.save_review is a task in docs/11-review.md.")

    # --- portability ------------------------------------------------------
    def export_table(self, table: str) -> Iterator[dict]:
        """Every row of a table, in the value forms the Store interface promises."""
        raise NotImplementedError("DuckDBStore.export_table is a task in docs/05-storage.md.")

    def import_table(self, table: str, rows: Iterable[dict]) -> None:
        """Insert rows produced by export_table. Rows whose key is already stored are skipped."""
        raise NotImplementedError("DuckDBStore.import_table is a task in docs/05-storage.md.")

    # --- analysis ---------------------------------------------------------
    def analytics(self):
        """A DuckDB connection for reading: a second cursor on this same database."""
        raise NotImplementedError("DuckDBStore.analytics is a task in docs/05-storage.md.")
