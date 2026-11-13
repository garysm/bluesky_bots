"""python -m bluesky_bots.topics check
python -m bluesky_bots.topics assign [--topic NAME]
"""
import argparse
import sys

from ..storage import open_store
from . import assign, get_topic, load_topics, resolve_accounts


def resolve(topics) -> None:
    """Look up any handles in these topics. Needs resolve_did from the backfill service (docs/04-backfill.md)."""
    if not any(t.handles for t in topics):
        return
    import httpx
    from ..backfill import resolve_did
    with httpx.Client(timeout=30) as client:
        resolve_accounts(topics, lambda handle: resolve_did(client, handle))


def check(args) -> int:
    try:
        topics = load_topics()
    except ValueError as e:
        print("error:", e)
        return 1
    for t in topics:
        dims = ", ".join(f"{n} ({len(d.values)} values)" for n, d in t.labels.dimensions.items()) if t.labels else "none"
        print(f"{t.name}: {'active' if t.active else 'inactive'}; {len(t.match.keywords)} keywords, "
              f"{len(t.match.patterns)} patterns, {len(t.match.accounts)} accounts; "
              f"entities: {', '.join(t.entities) or 'none'}; dimensions: {dims}")
    print(f"{len(topics)} topic files are valid")
    return 0


def run_assign(args) -> int:
    active = load_topics(active_only=True)
    topics = [get_topic(args.topic)] if args.topic else active
    resolve(topics + active)
    store = open_store()
    for t in topics:
        print(f"{t.name}: {assign(store, t)} posts")
    # The watch list is every account named in an active topic file.
    listed = set().union(*(t.dids for t in active)) if active else set()
    current = {r["did"] for r in store.export_table("accounts") if r["is_watchlist"]}
    store.upsert_accounts([{"did": d, "is_watchlist": True} for d in listed]
                          + [{"did": d, "is_watchlist": False} for d in current - listed])
    store.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bluesky_bots.topics", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="load every topic file and report what is in it")
    p = sub.add_parser("assign", help="recompute which stored posts belong to each topic")
    p.add_argument("--topic", help="one topic by name; default is every active topic")
    args = parser.parse_args()
    return {"check": check, "assign": run_assign}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
