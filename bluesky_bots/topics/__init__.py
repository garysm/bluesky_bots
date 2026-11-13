"""Topics service: what counts as part of a conversation.

A topic is one YAML file in topics/. This service loads and checks those
files, decides whether a post matches a topic, and records which stored
posts belong to which topic.

Guide: docs/02-topics.md. Command: python -m bluesky_bots.topics --help
"""
from .assign import assign
from .match import (capture_filter, entities_in, event_fields, keyword_regex, match_event,
                    match_post, match_text)
from .resolve import resolve_accounts
from .schema import Topic, get_topic, load_topic, load_topics

__all__ = ["Topic", "load_topic", "load_topics", "get_topic", "resolve_accounts", "keyword_regex",
           "match_text", "match_post", "event_fields", "match_event", "capture_filter",
           "entities_in", "assign"]
