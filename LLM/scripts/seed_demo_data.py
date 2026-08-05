"""Load deterministic DEMO_MOCK operational seed records."""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from operational_decision.operational.database import OperationalDatabase  # noqa: E402
from operational_decision.operational.seed_loader import (  # noqa: E402
    seed_operational_database,
)


async def seed_demo_data() -> None:
    """Initialize the operational DB and idempotently load demo records."""
    database = OperationalDatabase()
    await database.initialize()
    result = await seed_operational_database(database, PROJECT_ROOT / "data/seeds")
    print(
        "seed: "
        f"video_contexts={result.video_contexts}, "
        f"permissions={result.permissions}, "
        f"flight_plans={result.flight_plans}, "
        f"notams={result.notams}, "
        f"scenario_definitions={result.scenario_definitions}, "
        f"total_inserted={result.total_inserted}"
    )


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
