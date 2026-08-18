"""Operational SQLite database configuration."""

from pathlib import Path

from operational_decision.persistence.sqlite_database import SQLiteDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class OperationalDatabase(SQLiteDatabase):
    """Manage the independent operational-record SQLite database."""

    def __init__(self, path: Path = PROJECT_ROOT / "data/databases/operational.db") -> None:
        """Configure operational DB and its migration directory."""
        super().__init__(path, PROJECT_ROOT / "migrations/operational")
