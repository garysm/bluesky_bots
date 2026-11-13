"""python -m bluesky_bots.classify label --topic NAME [--tiered] [--limit N] [--verbose]
python -m bluesky_bots.classify train --topic NAME --dimension NAME [--from-model MODEL]
"""
import argparse
import asyncio
import sys
from datetime import datetime, timezone

from .. import config
from ..storage import open_store
from ..topics import get_topic
from . import (build_tiered_workflow, build_workflow, run_workflow, save_classifier, threshold_table,
               train_classifier, training_set)


def label(args) -> int:
    topic, store = get_topic(args.topic), open_store()
    workflow = build_tiered_workflow(topic, store) if args.tiered else build_workflow(topic, store)
    session = f"{topic.name}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"      # a new session per run
    print(asyncio.run(run_workflow(workflow, session, limit=args.limit, verbose=args.verbose)))
    store.close()
    return 0


def train(args) -> int:
    from ..narratives import embed_posts
    topic, store = get_topic(args.topic), open_store()
    rows = training_set(store, topic, args.dimension, args.from_model or config.model("LABEL_MODEL_STRONG"))
    if len(rows) < 40:
        print(f"only {len(rows)} labeled posts; label more before training")
        return 1
    clf, x_te, y_te = train_classifier(embed_posts(store, rows), [r["value"] for r in rows])
    print("saved", save_classifier(clf, topic, args.dimension))
    for row in threshold_table(clf, x_te, y_te):
        accuracy = "n/a" if row["accuracy"] is None else f"{row['accuracy']:.0%}"
        print(f"  threshold {row['threshold']}: settles {row['settled']:.0%}, accuracy {accuracy}")
    store.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bluesky_bots.classify", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("label", help="label a topic's unlabeled posts")
    p.add_argument("--topic", required=True)
    p.add_argument("--tiered", action="store_true", help="use the tiered workflow (docs/08-escalating-labels.md)")
    p.add_argument("--limit", type=int, default=200, help="most posts to label in this run")
    p.add_argument("--verbose", action="store_true", help="print each node's output")
    t = sub.add_parser("train", help="train the tier 0 classifier for one dimension")
    t.add_argument("--topic", required=True)
    t.add_argument("--dimension", required=True)
    t.add_argument("--from-model", help="whose labels to learn from; default is LABEL_MODEL_STRONG")
    args = parser.parse_args()
    return {"label": label, "train": train}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
