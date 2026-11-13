"""Storage service: the one place the project's data is written and deletes are honored.

    from bluesky_bots.storage import open_store
    store = open_store()                    # backend and location come from STORAGE_URL in .env
    store = open_store(read_only=True)      # for notebooks, reports and agent tools

Guide: docs/05-storage.md. Choosing a backend: docs/17-choosing-storage.md.
"""
from __future__ import annotations

from pathlib import Path

from .. import config
from .base import HUMAN_TIER, SCHEMA, TABLES, URI_TABLES, Store, copy_store, create_tables_sql, to_utc
from .records import event_to_row, load_events, load_raw_files

__all__ = ["open_store", "Store", "copy_store", "SCHEMA", "TABLES", "URI_TABLES", "HUMAN_TIER",
           "create_tables_sql", "to_utc", "event_to_row", "load_events", "load_raw_files"]


def _backend(scheme: str):
    if scheme == "duckdb":
        from .duckdb_store import DuckDBStore
        return DuckDBStore
    if scheme == "sqlite":
        from .sqlite_store import SQLiteStore
        return SQLiteStore
    raise ValueError(f"no storage backend for '{scheme}://'; known backends: duckdb, sqlite")


def open_store(url: str | None = None, read_only: bool = False) -> Store:
    """Open the store named by `url`, or by STORAGE_URL in .env.

    The scheme picks the backend, the rest is the location:
        duckdb:///data/narrative.duckdb      a path relative to the project root
        sqlite:///E:/big/narrative.sqlite    an absolute path
        sqlite://:memory:                    nothing on disk, for tests
    A store opened for writing has its tables created if they are missing.
    """
    url = url or config.STORAGE_URL
    scheme, sep, rest = url.partition("://")
    if not sep:
        raise ValueError(f"storage URL should look like duckdb:///path/to/file, got '{url}'")
    if rest != ":memory:":
        path = Path(rest.removeprefix("/"))
        rest = str(path if path.is_absolute() else config.ROOT / path)
    store = _backend(scheme)(rest, read_only=read_only)
    if not read_only:
        store.init_schema()
    return store
