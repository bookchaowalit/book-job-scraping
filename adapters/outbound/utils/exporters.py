"""
Data exporters — CSV, JSON, SQLite, Parquet.
Unified export interface for all scrapers.
"""

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime


class Exporter:
    """Unified data exporter for scraped results."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path("data/exported")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def to_csv(self, data: List[Dict], filename: str, fieldnames: List[str] = None) -> Path:
        if not data:
            return Path()
        filepath = self.output_dir / filename
        if not fieldnames:
            fieldnames = list(data[0].keys())
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)
        return filepath

    def to_json(self, data: List[Dict], filename: str) -> Path:
        if not data:
            return Path()
        filepath = self.output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return filepath

    def to_sqlite(self, data: List[Dict], db_name: str, table_name: str) -> Path:
        if not data:
            return Path()
        filepath = self.output_dir / db_name
        conn = sqlite3.connect(filepath)
        columns = list(data[0].keys())
        col_defs = ", ".join(f"{c} TEXT" for c in columns)
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({col_defs})")
        placeholders = ", ".join("?" for _ in columns)
        for row in data:
            values = [str(row.get(c, "")) for c in columns]
            conn.execute(f"INSERT INTO {table_name} VALUES ({placeholders})", values)
        conn.commit()
        conn.close()
        return filepath

    def to_parquet(self, data: List[Dict], filename: str) -> Path:
        """Export to Parquet (requires pandas + pyarrow)."""
        try:
            import pandas as pd
            filepath = self.output_dir / filename
            df = pd.DataFrame(data)
            df.to_parquet(filepath, index=False)
            return filepath
        except ImportError:
            print("Parquet export requires: pip install pandas pyarrow")
            return Path()
