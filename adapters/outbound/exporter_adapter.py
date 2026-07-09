"""
Exporter adapter — implements ExporterPort.
Supports: JSON, CSV, SQLite, Parquet
"""
import json
import csv
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

from core.models import ScrapedItem
from core.ports import ExporterPort


class ExporterAdapter:
    """
    Adapter for exporting scraped data to various formats.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent.parent / "data" / "exported"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def supported_formats(self) -> List[str]:
        return ["json", "csv", "sqlite", "parquet"]

    def export(self, items: List[ScrapedItem], format: str, filename: str) -> str:
        """Export items to specified format."""
        if format == "json":
            return self._export_json(items, filename)
        elif format == "csv":
            return self._export_csv(items, filename)
        elif format == "sqlite":
            return self._export_sqlite(items, filename)
        elif format == "parquet":
            return self._export_parquet(items, filename)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _export_json(self, items: List[ScrapedItem], filename: str) -> str:
        """Export to JSON."""
        filepath = self.output_dir / filename
        data = [item.to_dict() for item in items]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return str(filepath)

    def _export_csv(self, items: List[ScrapedItem], filename: str) -> str:
        """Export to CSV."""
        if not items:
            return ""
        filepath = self.output_dir / filename.replace(".csv", "") + ".csv"
        # Get all field names from first item
        fieldnames = list(items[0].to_dict().keys())
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in items:
                writer.writerow(item.to_dict())
        return str(filepath)

    def _export_sqlite(self, items: List[ScrapedItem], filename: str) -> str:
        """Export to SQLite database."""
        import sqlite3
        filepath = self.output_dir / filename.replace(".sqlite", "") + ".sqlite"
        conn = sqlite3.connect(filepath)
        cursor = conn.cursor()

        # Create table from first item's fields
        if items:
            fields = items[0].to_dict()
            columns = ", ".join([f"{k} TEXT" for k in fields.keys()])
            cursor.execute(f"CREATE TABLE IF NOT EXISTS items ({columns})")

            # Insert items
            placeholders = ", ".join(["?" for _ in fields])
            for item in items:
                values = [str(v) for v in item.to_dict().values()]
                cursor.execute(f"INSERT INTO items VALUES ({placeholders})", values)

        conn.commit()
        conn.close()
        return str(filepath)

    def _export_parquet(self, items: List[ScrapedItem], filename: str) -> str:
        """Export to Parquet (requires pandas + pyarrow)."""
        try:
            import pandas as pd
            filepath = self.output_dir / filename.replace(".parquet", "") + ".parquet"
            data = [item.to_dict() for item in items]
            df = pd.DataFrame(data)
            df.to_parquet(filepath, index=False)
            return str(filepath)
        except ImportError:
            raise ImportError("Parquet export requires: pip install pandas pyarrow")
