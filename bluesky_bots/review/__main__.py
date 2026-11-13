"""python -m bluesky_bots.review queue
python -m bluesky_bots.review accounts
python -m bluesky_bots.review account ACCOUNT DECISION --reviewer NAME [--notes TEXT]
python -m bluesky_bots.review posts --topic NAME
python -m bluesky_bots.review post NUMBER --topic NAME --reviewer NAME --set DIMENSION=VALUE [--target ENTITY]
"""
import argparse
import sys

from ..storage import open_store
from ..topics import get_topic
from . import DECISIONS, decide_account, decide_post, pending_accounts, pending_posts, queue_flagged


def queue(args, store) -> None:
    print(f"{queue_flagged(store)} flagged accounts are on the queue")


def accounts(args, store) -> None:
    for item in pending_accounts(store):
        print(item["account"])
        for e in item["evidence"]:
            print(f"    {e['signal']:22} {e['observed']}")


def account(args, store) -> None:
    decide_account(store, args.account, args.reviewer, args.decision, args.notes)
    print("recorded")


def posts(args, store) -> None:
    for n, item in enumerate(pending_posts(store, get_topic(args.topic)), 1):
        print(f"{n}. {item['text']}")
        if item["parent_text"]:
            print(f"   in reply to: {item['parent_text']}")
        for label in item["labels"]:
            about = f" (about {label['target']})" if label["target"] else ""
            print(f"   {label['dimension']} = {label['value']}{about}")


def post(args, store) -> None:
    topic = get_topic(args.topic)
    items = pending_posts(store, topic)
    if not 1 <= args.number <= len(items):
        raise SystemExit(f"there are {len(items)} queued posts; run 'posts --topic {topic.name}' to list them")
    values = dict(pair.split("=", 1) for pair in args.set)
    decide_post(store, topic, items[args.number - 1]["uri"], args.reviewer, values, args.target)
    print("recorded")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bluesky_bots.review", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("queue", help="put flagged accounts on the queue")
    sub.add_parser("accounts", help="list queued accounts with their evidence")
    a = sub.add_parser("account", help="record a decision about a queued account")
    a.add_argument("account", help="the anonymous ID shown by 'accounts'")
    a.add_argument("decision", choices=DECISIONS)
    a.add_argument("--reviewer", required=True)
    a.add_argument("--notes", default="")
    p = sub.add_parser("posts", help="list a topic's queued posts")
    p.add_argument("--topic", required=True)
    d = sub.add_parser("post", help="record your label for a queued post")
    d.add_argument("number", type=int, help="the number shown by 'posts'")
    d.add_argument("--topic", required=True)
    d.add_argument("--reviewer", required=True)
    d.add_argument("--set", action="append", required=True, metavar="DIMENSION=VALUE")
    d.add_argument("--target", default="", help="the entity the label is about, if any")
    args = parser.parse_args()
    store = open_store()
    {"queue": queue, "accounts": accounts, "account": account, "posts": posts, "post": post}[args.command](args, store)
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
