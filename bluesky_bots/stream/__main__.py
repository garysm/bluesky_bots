"""python -m bluesky_bots.stream [--all]

Runs until stopped with Ctrl+C. Run it in a terminal, not a notebook.
"""
import argparse
import asyncio

from .. import config
from ..topics import capture_filter, load_topics
from ..topics.__main__ import resolve
from . import consume, every, load_cursor, make_handler, save_cursor

COLLECTIONS = ["app.bsky.feed.post", "app.bsky.feed.repost"]
CURSOR_FILE = config.STATE_DIR / "cursor.json"


async def run(keep) -> None:
    state = {"cursor": load_cursor(CURSOR_FILE)}
    handle = make_handler(keep, config.RAW_DIR, state)

    def save() -> None:
        if state["cursor"] is not None:
            save_cursor(CURSOR_FILE, state["cursor"])

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(every(5, save))
            tg.create_task(consume(COLLECTIONS, handle, cursor=state["cursor"]))
    finally:
        save()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m bluesky_bots.stream", description=__doc__)
    parser.add_argument("--all", action="store_true",
                        help="keep every event instead of only those matching an active topic "
                             "(roughly 5 million a day; see docs/17-choosing-storage.md)")
    args = parser.parse_args()
    if args.all:
        keep = lambda event: True
        print("keeping every event")
    else:
        topics = load_topics(active_only=True)
        resolve(topics)
        keep = capture_filter(topics)
        print("keeping events that match:", ", ".join(t.name for t in topics) or "(no active topics: deletes only)")
    print("writing to", config.RAW_DIR)
    try:
        asyncio.run(run(keep))
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
