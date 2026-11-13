"""Stream service: listen to Bluesky through Jetstream and keep what a `keep` function accepts.

It writes hourly landing files and never opens the database. It does not
know what a topic is: the command passes it a `keep` function built by the
topics service.

Guide: docs/03-stream.md. Command: python -m bluesky_bots.stream --help
"""
from .consumer import build_url, consume
from .landing import every, hour_file, load_cursor, make_handler, save_cursor

__all__ = ["build_url", "consume", "hour_file", "make_handler", "save_cursor", "load_cursor", "every"]
