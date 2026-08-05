"""Idempotent deterministic DEMO_MOCK seed loading."""

import json
from dataclasses import dataclass
from pathlib import Path

from operational_decision.context.context_repository import ContextRepository
from operational_decision.contracts.context import VideoContextRecord
from operational_decision.operational.database import OperationalDatabase
from operational_decision.operational.flight_plan_repository import FlightPlanRepository
from operational_decision.operational.notam_repository import NotamRepository
from operational_decision.operational.permission_repository import PermissionRepository
from operational_decision.persistence.sqlite_database import parse_utc


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Counts of newly inserted deterministic records."""

    video_contexts: int
    permissions: int
    flight_plans: int
    notams: int
    scenario_definitions: int

    @property
    def total_inserted(self) -> int:
        """Return the number of records newly added by this run."""
        return (
            self.video_contexts
            + self.permissions
            + self.flight_plans
            + self.notams
            + self.scenario_definitions
        )


def _load_seed_list(path: Path) -> list[dict[str, object]]:
    """Load a seed JSON array and enforce DEMO_MOCK provenance."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"seed file must contain an object array: {path}")
    records: list[dict[str, object]] = value
    if any(record.get("source_type") != "DEMO_MOCK" for record in records):
        raise ValueError(f"every seed record must use DEMO_MOCK: {path}")
    return records


async def _exists(database: OperationalDatabase, table: str, key: str, value: object) -> bool:
    """Check a row against a fixed allowlisted table and key pair."""
    queries = {
        ("video_contexts", "video_id"): "SELECT 1 FROM video_contexts WHERE video_id = ?",
        ("permissions", "permission_id"): "SELECT 1 FROM permissions WHERE permission_id = ?",
        ("flight_plans", "flight_plan_id"): "SELECT 1 FROM flight_plans WHERE flight_plan_id = ?",
        ("notams", "notam_id"): "SELECT 1 FROM notams WHERE notam_id = ?",
    }
    try:
        query = queries[(table, key)]
    except KeyError as exc:
        raise ValueError("unsupported seed existence query") from exc
    async with database.connection() as connection:
        return await (await connection.execute(query, (value,))).fetchone() is not None


async def seed_operational_database(
    database: OperationalDatabase, seed_directory: Path
) -> SeedResult:
    """Load deterministic operational seeds without duplicates or tool logic."""
    context_repository = ContextRepository(database)
    permission_repository = PermissionRepository(database)
    flight_plan_repository = FlightPlanRepository(database)
    notam_repository = NotamRepository(database)
    counts = {"video_contexts": 0, "permissions": 0, "flight_plans": 0, "notams": 0}

    for row in _load_seed_list(seed_directory / "video_contexts.json"):
        exists = await _exists(database, "video_contexts", "video_id", row["video_id"])
        await context_repository.upsert(
            VideoContextRecord.model_validate_json(json.dumps(row, ensure_ascii=False))
        )
        if not exists:
            counts["video_contexts"] += 1

    for row in _load_seed_list(seed_directory / "permissions.json"):
        if await _exists(database, "permissions", "permission_id", row["permission_id"]):
            continue
        row["valid_from_utc"] = parse_utc(str(row["valid_from_utc"]))
        row["valid_to_utc"] = parse_utc(str(row["valid_to_utc"]))
        await permission_repository.upsert(row)
        counts["permissions"] += 1

    for row in _load_seed_list(seed_directory / "flight_plans.json"):
        if await _exists(database, "flight_plans", "flight_plan_id", row["flight_plan_id"]):
            continue
        row["planned_departure_utc"] = parse_utc(str(row["planned_departure_utc"]))
        if row.get("planned_arrival_utc") is not None:
            row["planned_arrival_utc"] = parse_utc(str(row["planned_arrival_utc"]))
        await flight_plan_repository.upsert(row)
        counts["flight_plans"] += 1

    for row in _load_seed_list(seed_directory / "notams.json"):
        if await _exists(database, "notams", "notam_id", row["notam_id"]):
            continue
        row["valid_from_utc"] = parse_utc(str(row["valid_from_utc"]))
        row["valid_to_utc"] = parse_utc(str(row["valid_to_utc"]))
        await notam_repository.upsert(row)
        counts["notams"] += 1

    scenarios = _load_seed_list(seed_directory / "demo_scenarios.json")
    return SeedResult(
        video_contexts=counts["video_contexts"],
        permissions=counts["permissions"],
        flight_plans=counts["flight_plans"],
        notams=counts["notams"],
        scenario_definitions=len(scenarios) if sum(counts.values()) > 0 else 0,
    )
