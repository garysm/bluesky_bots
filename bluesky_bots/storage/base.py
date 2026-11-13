"""The storage contract: the tables, and the operations every backend provides.

A backend is one class with these methods. `sqlite_store.py` is a complete one
to read; `duckdb_store.py` is the one the guide builds. A backend is finished
when tests/test_store_contract.py passes for it.

Values that cross the interface, whatever the backend stores underneath:

- timestamps: timezone-aware `datetime` in UTC. ISO strings are accepted on the way in.
- dates: `datetime.date`
- booleans: `bool`
- vectors: one-dimensional `numpy.ndarray` of float32
- signal evidence: a dict on the way in, JSON text on the way out
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable, Iterator, Protocol

import numpy as np


@dataclass(frozen=True)
class Table:
    name: str
    columns: dict[str, str]        # column name -> logical type (see SQL_TYPES)
    key: tuple[str, ...] = ()      # primary key; empty for append-only tables


SCHEMA: tuple[Table, ...] = (
    # One row per post, with links to the post it replies to or quotes.
    Table("posts", {"uri": "text", "did": "text", "created_at": "timestamp", "text": "text",
                    "lang": "text", "reply_parent": "text", "reply_root": "text",
                    "quote_of": "text", "source": "text"}, ("uri",)),
    # One row per repost.
    Table("reposts", {"uri": "text", "did": "text", "subject_uri": "text",
                      "created_at": "timestamp"}, ("uri",)),
    # One row per account.
    Table("accounts", {"did": "text", "handle": "text", "created_at": "timestamp",
                       "description": "text", "is_watchlist": "bool",
                       "self_declared_bot": "bool", "fetched_at": "timestamp"}, ("did",)),
    # Which topics a post belongs to, and which rule put it there.
    Table("post_topic", {"uri": "text", "topic": "text", "matched_by": "text",
                         "assigned_at": "timestamp"}, ("uri", "topic")),
    # One row per post, topic, scheme version, model, target and dimension.
    # target is an entity name from the topic, or '' for the post as a whole.
    Table("labels", {"uri": "text", "topic": "text", "scheme_version": "text", "model": "text",
                     "target": "text", "dimension": "text", "value": "text",
                     "confidence": "float", "tier": "int", "labeled_at": "timestamp"},
          ("uri", "topic", "scheme_version", "model", "target", "dimension")),
    # One vector per post and embedding model.
    Table("embeddings", {"uri": "text", "model": "text", "vector": "vector"}, ("uri", "model")),
    # Which narrative a post was placed in, per topic and clustering run.
    Table("post_narrative", {"uri": "text", "topic": "text", "run_date": "date",
                             "narrative_id": "int"}, ("uri", "topic", "run_date")),
    Table("narratives", {"topic": "text", "narrative_id": "int", "run_date": "date",
                         "name": "text", "summary": "text", "n_posts": "int"},
          ("topic", "narrative_id", "run_date")),
    # One row per account, signal and window, with what was observed as JSON.
    Table("signals", {"did": "text", "signal": "text", "window_start": "timestamp",
                      "value": "float", "evidence": "json", "computed_at": "timestamp"}),
    # A reviewer's decision about an account.
    Table("reviews", {"did": "text", "reviewer": "text", "decision": "text", "notes": "text",
                      "reviewed_at": "timestamp"}),
    # What is waiting for a person: item_type is 'post' or 'account'.
    Table("review_queue", {"item_type": "text", "item_id": "text", "topic": "text",
                           "reason": "text", "queued_at": "timestamp"},
          ("item_type", "item_id", "topic")),
)
TABLES: dict[str, Table] = {t.name: t for t in SCHEMA}

# Every table keyed by a record's AT URI. A delete has to reach all of them.
URI_TABLES = ("posts", "reposts", "post_topic", "labels", "embeddings", "post_narrative")

# The tier recorded for a label a person set. Higher than any model tier,
# so the labels_final view prefers it.
HUMAN_TIER = 9

SQL_TYPES = {
    "duckdb": {"text": "TEXT", "timestamp": "TIMESTAMPTZ", "date": "DATE", "bool": "BOOLEAN",
               "int": "INTEGER", "float": "DOUBLE", "json": "JSON", "vector": "FLOAT[]"},
    "sqlite": {"text": "TEXT", "timestamp": "TEXT", "date": "TEXT", "bool": "INTEGER",
               "int": "INTEGER", "float": "REAL", "json": "TEXT", "vector": "BLOB"},
}


def create_tables_sql(dialect: str) -> str:
    """The CREATE TABLE statements for every table in SCHEMA, in one string."""
    types, false = SQL_TYPES[dialect], "0" if dialect == "sqlite" else "FALSE"
    statements = []
    for table in SCHEMA:
        cols = []
        for name, kind in table.columns.items():
            col = f"{name} {types[kind]}"
            if kind == "bool":
                col += f" DEFAULT {false}"
            cols.append(col)
        if table.key:
            cols.append(f"PRIMARY KEY ({', '.join(table.key)})")
        statements.append(f"CREATE TABLE IF NOT EXISTS {table.name} (\n  " + ",\n  ".join(cols) + ");")
    return "\n".join(statements)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_utc(value: Any) -> datetime | None:
    """A timezone-aware UTC datetime from a datetime or an ISO string.

    Returns None for None and for text that is not a date: `createdAt` is
    written by the author's app and can be anything. A value with no time
    zone is taken to be UTC.
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_date(value: Any) -> date | None:
    if value is None or (isinstance(value, date) and not isinstance(value, datetime)):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(value)


class Store(Protocol):
    """What every storage backend provides. Rows are plain dicts keyed by column name."""

    url: str
    read_only: bool

    def init_schema(self) -> None:
        """Create the tables if they are missing. Safe to call every time."""

    def close(self) -> None: ...

    # --- ingest -----------------------------------------------------------
    def add_posts(self, rows: Iterable[dict]) -> None:
        """Insert posts. A row whose uri is already stored is skipped."""

    def add_reposts(self, rows: Iterable[dict]) -> None:
        """Insert reposts. A row whose uri is already stored is skipped."""

    def upsert_accounts(self, rows: Iterable[dict]) -> None:
        """Create accounts or update them. A column that is missing or None keeps its stored value."""

    def delete_record(self, uri: str) -> None:
        """Remove a record its author deleted from every table in URI_TABLES and from the review queue."""

    # --- fetch ------------------------------------------------------------
    def iter_posts(self) -> Iterator[dict]:
        """Every stored post."""

    def posts_in_topic(self, topic: str, since: datetime | None = None,
                       until: datetime | None = None) -> list[dict]:
        """Posts assigned to a topic, oldest first, each with `parent_text`
        (the text of the post it replies to, when that post is stored)."""

    def unlabeled_posts(self, topic: str, scheme_version: str, model: str | None = None,
                        limit: int | None = None) -> list[dict]:
        """Posts in a topic with no label under this scheme version (from `model`, or from any model)."""

    # --- derived data -----------------------------------------------------
    def set_post_topics(self, topic: str, rows: Iterable[dict]) -> None:
        """Replace a topic's membership with `rows` (each has uri and matched_by)."""

    def save_labels(self, rows: Iterable[dict]) -> None:
        """Store label rows. A row with the same key replaces the old one."""

    def save_vectors(self, model: str, vectors: dict[str, np.ndarray]) -> None:
        """Store one vector per uri for an embedding model."""

    def load_vectors(self, model: str, uris: Iterable[str] | None = None) -> dict[str, np.ndarray]:
        """The stored vectors for these uris (or all of them), keyed by uri."""

    def save_narratives(self, topic: str, run_date: date, narratives: Iterable[dict],
                        assignments: Iterable[dict]) -> None:
        """Replace one clustering run: narratives (narrative_id, name, summary, n_posts)
        and assignments (uri, narrative_id)."""

    def narrative_run(self, topic: str, before: date | None = None) -> dict | None:
        """The latest clustering run for a topic (earlier than `before`, if given), as
        {"run_date", "narratives", "assignments"}, or None when there is none."""

    def save_signals(self, rows: Iterable[dict]) -> None:
        """Append signal rows (did, signal, value, evidence, and optionally window_start)."""

    def enqueue_review(self, rows: Iterable[dict]) -> None:
        """Add items for a person to look at. An item already queued is left alone."""

    def pending_reviews(self, item_type: str | None = None, topic: str | None = None) -> list[dict]:
        """Queued items, oldest first."""

    def resolve_review(self, item_type: str, item_id: str, topic: str = "") -> None:
        """Take an item off the queue."""

    def save_review(self, row: dict) -> None:
        """Record a reviewer's decision about an account."""

    # --- portability ------------------------------------------------------
    def export_table(self, table: str) -> Iterator[dict]:
        """Every row of a table, in the value forms listed at the top of this module."""

    def import_table(self, table: str, rows: Iterable[dict]) -> None:
        """Insert rows produced by export_table. Rows whose key is already stored are skipped."""

    # --- analysis ---------------------------------------------------------
    def analytics(self):
        """A DuckDB connection for reading, with every table and the views in
        views.py visible by name. Analysis SQL is written against this,
        whichever backend holds the data."""


def copy_store(src: Store, dst: Store) -> dict[str, int]:
    """Copy every table from one backend to another. Returns rows copied per table."""
    counts = {}
    for table in SCHEMA:
        rows = list(src.export_table(table.name))
        dst.import_table(table.name, rows)
        counts[table.name] = len(rows)
    return counts
