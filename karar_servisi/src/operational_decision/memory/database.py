"""Event-memory SQLite database configuration."""

from pathlib import Path

from operational_decision.persistence.sqlite_database import SQLiteDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class EventMemoryDatabase(SQLiteDatabase):
    """Manage the independent event-memory SQLite database."""

    def __init__(self, path: Path = PROJECT_ROOT / "data/databases/event_memory.db") -> None:
        """Configure event-memory DB and its migration directory."""
        super().__init__(path, PROJECT_ROOT / "migrations/event_memory")
