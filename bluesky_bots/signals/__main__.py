"""python -m bluesky_bots.signals"""
import argparse
import sys

from ..storage import open_store
from . import compute_signals


def main() -> int:
    argparse.ArgumentParser(prog="python -m bluesky_bots.signals", description=__doc__).parse_args()
    store = open_store()
    for signal, n in sorted(compute_signals(store).items()):
        print(f"  {signal:24}{n:>8} rows")
    flagged = store.analytics().execute("SELECT count(*) FROM flagged").fetchone()[0]
    print(f"{flagged} accounts have two or more different signals (unreviewed)")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
