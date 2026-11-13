"""python -m bluesky_bots.storage init
python -m bluesky_bots.storage load [--all]
python -m bluesky_bots.storage info
python -m bluesky_bots.storage copy --from URL --to URL
"""
import argparse
import sys

from .. import config
from . import SCHEMA, copy_store, load_raw_files, open_store


def init(args) -> int:
    open_store().close()
    print("tables are ready in", config.STORAGE_URL)
    return 0


def load(args) -> int:
    store = open_store()
    n = load_raw_files(store, config.RAW_DIR, keep_newest=not args.all)
    store.close()
    print(f"loaded {n} landing files from {config.RAW_DIR}")
    return 0


def info(args) -> int:
    store = open_store(read_only=True)
    con = store.analytics()
    print(config.STORAGE_URL)
    for table in SCHEMA:
        print(f"  {table.name:16}{con.execute(f'SELECT count(*) FROM {table.name}').fetchone()[0]:>10}")
    store.close()
    return 0


def copy(args) -> int:
    src, dst = open_store(args.source, read_only=True), open_store(args.to)
    for table, n in copy_store(src, dst).items():
        print(f"  {table:16}{n:>10}")
    src.close()
    dst.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bluesky_bots.storage", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create the tables")
    p = sub.add_parser("load", help="move the stream's landing files into the store")
    p.add_argument("--all", action="store_true", help="include the newest file (only when the stream is stopped)")
    sub.add_parser("info", help="row counts per table")
    c = sub.add_parser("copy", help="copy every table from one backend to another")
    c.add_argument("--from", dest="source", required=True, help="for example duckdb:///data/narrative.duckdb")
    c.add_argument("--to", required=True, help="for example sqlite:///data/narrative.sqlite")
    args = parser.parse_args()
    return {"init": init, "load": load, "info": info, "copy": copy}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
