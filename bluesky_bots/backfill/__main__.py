"""python -m bluesky_bots.backfill posts --topic NAME --start YYYY-MM-DD [--end YYYY-MM-DD]
python -m bluesky_bots.backfill accounts [--limit N]
"""
import argparse
import sys
import time
from datetime import datetime, timezone

import httpx

from ..storage import open_store
from ..topics import assign, get_topic, resolve_accounts
from . import account_created, author_history, post_to_row, resolve_did, search_posts


def day(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def posts(args) -> int:
    """A topic's history: every search it lists, and the feed of every account it names."""
    topic = get_topic(args.topic)
    start, end = day(args.start), day(args.end) if args.end else datetime.now(timezone.utc)
    store = open_store()
    with httpx.Client(timeout=30) as client:
        resolve_accounts([topic], lambda handle: resolve_did(client, handle))
        for query in topic.search:
            store.add_posts(post_to_row(p, "backfill_search") for p in search_posts(client, query, start, end))
        for did in sorted(topic.dids):
            feed = author_history(client, did, start)
            # Items with a "reason" are reposts of someone else's post; those are left out here.
            store.add_posts(post_to_row(item["post"], "backfill_feed") for item in feed if "reason" not in item)
    print(f"{topic.name}: {assign(store, topic)} posts in the topic")
    store.close()
    return 0


def accounts(args) -> int:
    """Creation dates for accounts that have posts stored but no date yet. The age signal needs them."""
    store = open_store()
    dids = [row[0] for row in store.analytics().execute("""
        SELECT DISTINCT p.did FROM posts p LEFT JOIN accounts a USING (did)
        WHERE a.created_at IS NULL ORDER BY 1 LIMIT ?""", [args.limit]).fetchall()]
    with httpx.Client(timeout=30) as client:
        for did in dids:
            store.upsert_accounts([{"did": did, "created_at": account_created(client, did),
                                    "fetched_at": datetime.now(timezone.utc)}])
            time.sleep(0.2)
    print(f"fetched creation dates for {len(dids)} accounts")
    store.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bluesky_bots.backfill", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("posts", help="fetch a topic's history from search and author feeds")
    p.add_argument("--topic", required=True)
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", help="YYYY-MM-DD; default is now")
    a = sub.add_parser("accounts", help="fetch creation dates for accounts seen in stored posts")
    a.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    return {"posts": posts, "accounts": accounts}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
