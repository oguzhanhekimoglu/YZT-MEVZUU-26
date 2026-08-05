"""Initialize both local SQLite databases from tracked migrations."""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from operational_decision.memory.database import EventMemoryDatabase  # noqa: E402
from operational_decision.operational.database import OperationalDatabase  # noqa: E402


async def initialize_databases() -> None:
    """Apply pending operational and event-memory migrations."""
    databases = (OperationalDatabase(), EventMemoryDatabase())
    for database in databases:
        migrations = await database.initialize()
        label = database.path.name
        if migrations:
            print(f"{label}: applied {', '.join(migrations)}")
        else:
            print(f"{label}: no pending migrations")


if __name__ == "__main__":
    asyncio.run(initialize_databases())
