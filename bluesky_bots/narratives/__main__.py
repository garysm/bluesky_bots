"""python -m bluesky_bots.narratives --topic NAME [--days 7]"""
import argparse
import sys

from ..storage import open_store
from ..topics import get_topic
from . import run_topic


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bluesky_bots.narratives", description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--days", type=int, default=7, help="how many days of posts to cluster")
    args = parser.parse_args()
    topic, store = get_topic(args.topic), open_store()
    result = run_topic(store, topic, days=args.days)
    print(f"{topic.name}: {result['posts']} posts, {result['narratives']} narratives, "
          f"{result['unclustered']} in no narrative")
    run = store.narrative_run(topic.name)
    for n in sorted(run["narratives"] if run else [], key=lambda n: -n["n_posts"]):
        print(f"  {n['narrative_id']:>4}  {n['n_posts']:>6}  {n['name']}")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
