"""
Utility functions shared across the ABC Phones data pipeline.
"""

import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize all column names to lowercase with underscores instead of spaces.
    Removes special characters, trailing whitespace, and normalises separators.
    Applies immediately after loading any dataset.
    """
    renames = {}
    for col in df.columns:
        new = (
            col.strip()
            .lower()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("(", "")
            .replace(")", "")
            .replace(",", "")
            .replace("?", "")
            .replace("–", "-")
            .replace("-", "_")
        )
        # Collapse multiple underscores
        while "__" in new:
            new = new.replace("__", "_")
        new = new.strip("_")
        renames[col] = new
    return df.rename(columns=renames)
