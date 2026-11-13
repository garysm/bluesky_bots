"""The only way data leaves the project.

Guide: docs/13-reports.md (step 2).
"""
import pandas as pd

# Columns that name a person, or that can be searched to find one.
FORBIDDEN = {"did", "handle", "display_name", "uri", "text", "description"}


def export_public(df: pd.DataFrame, path: str, count_col: str, min_cell: int = 10) -> pd.DataFrame:
    """Write a frame to CSV, refusing identifying columns and hiding small counts.

    Raises ValueError if the frame has any column in FORBIDDEN. Rows whose
    `count_col` is under `min_cell` are dropped. Returns what was written.
    """
    raise NotImplementedError("export_public is a task in docs/13-reports.md.")
