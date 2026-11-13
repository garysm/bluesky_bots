"""python -m bluesky_bots.agent "Draft two paragraphs on stance in dem-leadership, 2026-10-20 to 2026-11-17."

Prints each tool call and its result, then the draft.
"""
import argparse
import asyncio
import sys

from google.adk.runners import InMemoryRunner

from . import build_analyst


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bluesky_bots.agent", description=__doc__)
    parser.add_argument("request")
    args = parser.parse_args()
    runner = InMemoryRunner(agent=build_analyst(), app_name="analyst")
    asyncio.run(runner.run_debug(args.request, verbose=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
