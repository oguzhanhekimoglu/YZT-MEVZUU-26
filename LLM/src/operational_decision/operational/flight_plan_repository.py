"""Persistence-only flight-plan repository."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from operational_decision.operational.database import OperationalDatabase
from operational_decision.persistence.sqlite_database import parse_utc, serialize_utc


class FlightPlanRepository:
    """Store and read flight plans without treating them as permissions."""

    def __init__(self, database: OperationalDatabase) -> None:
        """Bind the repository to an operational database."""
        self.database = database

    async def upsert(self, record: Mapping[str, object]) -> None:
        """Insert or update one flight-plan row."""
        departure = record["planned_departure_utc"]
        arrival = record.get("planned_arrival_utc")
        if not isinstance(departure, datetime):
            raise TypeError("planned_departure_utc must be a datetime")
        if arrival is not None and not isinstance(arrival, datetime):
            raise TypeError("planned_arrival_utc must be a datetime or None")
        async with self.database.transaction() as connection:
            await connection.execute(
                """INSERT INTO flight_plans (
                    flight_plan_id, platform_id, registration_mark, callsign, context_id,
                    operational_area_id, scenario_id, departure_aerodrome, arrival_aerodrome,
                    planned_departure_utc, planned_arrival_utc, route_or_area,
                    flight_plan_status, source_type, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(flight_plan_id) DO UPDATE SET
                    platform_id = excluded.platform_id,
                    registration_mark = excluded.registration_mark,
                    callsign = excluded.callsign,
                    context_id = excluded.context_id,
                    operational_area_id = excluded.operational_area_id,
                    scenario_id = excluded.scenario_id,
                    departure_aerodrome = excluded.departure_aerodrome,
                    arrival_aerodrome = excluded.arrival_aerodrome,
                    planned_departure_utc = excluded.planned_departure_utc,
                    planned_arrival_utc = excluded.planned_arrival_utc,
                    route_or_area = excluded.route_or_area,
                    flight_plan_status = excluded.flight_plan_status,
                    source_type = excluded.source_type,
                    notes = excluded.notes""",
                (
                    record["flight_plan_id"],
                    record["platform_id"],
                    record.get("registration_mark"),
                    record.get("callsign"),
                    record["context_id"],
                    record.get("operational_area_id"),
                    record.get("scenario_id"),
                    record.get("departure_aerodrome"),
                    record.get("arrival_aerodrome"),
                    serialize_utc(departure),
                    serialize_utc(arrival) if arrival is not None else None,
                    record.get("route_or_area"),
                    record["flight_plan_status"],
                    record.get("source_type", "DEMO_MOCK"),
                    record.get("notes"),
                ),
            )

    async def find_by_platform(self, platform_id: str) -> list[dict[str, Any]]:
        """Return all stored plans for one platform without domain interpretation."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM flight_plans WHERE platform_id = ? ORDER BY planned_departure_utc",
                (platform_id,),
            )
            rows = await cursor.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            mapped = dict(row)
            mapped["planned_departure_utc"] = parse_utc(mapped["planned_departure_utc"])
            if mapped["planned_arrival_utc"] is not None:
                mapped["planned_arrival_utc"] = parse_utc(mapped["planned_arrival_utc"])
            result.append(mapped)
        return result

    async def find_by_platform_and_context(
        self, platform_id: str, context_id: str
    ) -> list[dict[str, Any]]:
        """Return all plans in one context for deterministic classification."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """SELECT * FROM flight_plans
                WHERE platform_id = ? AND context_id = ?
                ORDER BY planned_departure_utc, flight_plan_id""",
                (platform_id, context_id),
            )
            rows = await cursor.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            mapped = dict(row)
            mapped["planned_departure_utc"] = parse_utc(mapped["planned_departure_utc"])
            if mapped["planned_arrival_utc"] is not None:
                mapped["planned_arrival_utc"] = parse_utc(mapped["planned_arrival_utc"])
            result.append(mapped)
        return result
