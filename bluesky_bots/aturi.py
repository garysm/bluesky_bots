"""AT URIs: the address of a record, written at://<did>/<collection>/<rkey>.

Guide: docs/02-topics.md (step 4) and docs/05-storage.md (step 2).
"""
from __future__ import annotations


def at_uri(event: dict) -> str:
    """The AT URI of the record a Jetstream event is about, built from its did, collection and rkey."""
    raise NotImplementedError("at_uri is a task in docs/02-topics.md.")


def did_of(uri: str) -> str:
    """The DID inside an AT URI."""
    raise NotImplementedError("did_of is a task in docs/02-topics.md.")


def quoted_uri(record: dict) -> str | None:
    """The URI of the post a record quotes, or None if it quotes nothing.

    Handles both shapes: a plain quote (embed.record.uri) and a quote that
    also carries images or video (embed.record.record.uri).
    """
    raise NotImplementedError("quoted_uri is a task in docs/02-topics.md.")
