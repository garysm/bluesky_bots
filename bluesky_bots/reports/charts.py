"""The core chart: posts per day with and without flagged accounts.

Guide: docs/13-reports.md (steps 3 and 4).
"""
import pandas as pd
import plotly.express as px

from ..topics import Topic

SERIES = ["all_accounts", "excluding_flagged", "self_declared_bots"]


def label_counts_by_day(con, topic: Topic, dimension: str, value: str, start: str, end: str,
                        target: str | None = None) -> pd.DataFrame:
    """Per day, how many of a topic's posts carry `value` on `dimension`, as three series.

    all_accounts, excluding_flagged (accounts in the `flagged` view left out)
    and self_declared_bots. start and end are dates as YYYY-MM-DD, both
    included. target limits the count to labels about one entity.
    """
    raise NotImplementedError("label_counts_by_day is a task in docs/13-reports.md.")


def label_chart(con, topic: Topic, dimension: str, value: str, start: str, end: str,
                target: str | None = None):
    """The numbers from label_counts_by_day and a line chart of them.

    Returns (DataFrame, figure). The topic's markers are drawn as dotted
    vertical lines.
    """
    raise NotImplementedError("label_chart is a task in docs/13-reports.md.")
