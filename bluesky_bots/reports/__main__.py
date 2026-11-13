"""python -m bluesky_bots.reports --topic NAME --dimension NAME --value VALUE --start YYYY-MM-DD --end YYYY-MM-DD [--target ENTITY]

Writes a chart (HTML) and the daily numbers behind it (CSV) to the out folder.
"""
import argparse
import sys

from .. import config
from ..storage import open_store
from ..topics import get_topic
from . import export_public, label_chart


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bluesky_bots.reports", description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--dimension", required=True)
    parser.add_argument("--value", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--target", help="count only labels about this entity")
    args = parser.parse_args()

    topic, store = get_topic(args.topic), open_store(read_only=True)
    df, fig = label_chart(store.analytics(), topic, args.dimension, args.value, args.start, args.end,
                          args.target)
    store.close()
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = "-".join(filter(None, [topic.name, args.dimension, args.value, args.target]))
    fig.write_html(config.OUT_DIR / f"{stem}.html")
    written = export_public(df, config.OUT_DIR / f"{stem}.csv", count_col="all_accounts")
    print(f"wrote {stem}.html and {stem}.csv ({len(written)} of {len(df)} days have 10 or more posts) "
          f"to {config.OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
