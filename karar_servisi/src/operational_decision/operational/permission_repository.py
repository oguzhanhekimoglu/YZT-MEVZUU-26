"""Persistence-only permission record repository."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from operational_decision.operational.database import OperationalDatabase
from operational_decision.persistence.sqlite_database import parse_utc, serialize_utc


class PermissionRepository:
    """Store and query permission rows without deriving domain status."""

    def __init__(self, database: OperationalDatabase) -> None:
        """Bind the repository to an operational database."""
        self.database = database

    async def upsert(self, record: Mapping[str, object]) -> None:
        """Insert or update one permission using fixed parameterized SQL."""
        valid_from = record["valid_from_utc"]
        valid_to = record["valid_to_utc"]
        if not isinstance(valid_from, datetime) or not isinstance(valid_to, datetime):
            raise TypeError("permission validity fields must be datetime values")
        issued_at = record.get("issued_at_utc")
        if issued_at is not None and not isinstance(issued_at, datetime):
            raise TypeError("issued_at_utc must be a datetime or None")
        async with self.database.transaction() as connection:
            await connection.execute(
                """INSERT INTO permissions (
                    permission_id, platform_id, registration_mark, operator_name, context_id,
                    operational_area_id, scenario_id, flight_purpose, flight_type,
                    valid_from_utc, valid_to_utc, altitude_ft_msl, departure_aerodrome,
                    arrival_aerodrome, permission_status, issued_at_utc, source_type, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(permission_id) DO UPDATE SET
                    platform_id = excluded.platform_id,
                    registration_mark = excluded.registration_mark,
                    operator_name = excluded.operator_name,
                    context_id = excluded.context_id,
                    operational_area_id = excluded.operational_area_id,
                    scenario_id = excluded.scenario_id,
                    flight_purpose = excluded.flight_purpose,
                    flight_type = excluded.flight_type,
                    valid_from_utc = excluded.valid_from_utc,
                    valid_to_utc = excluded.valid_to_utc,
                    altitude_ft_msl = excluded.altitude_ft_msl,
                    departure_aerodrome = excluded.departure_aerodrome,
                    arrival_aerodrome = excluded.arrival_aerodrome,
                    permission_status = excluded.permission_status,
                    issued_at_utc = excluded.issued_at_utc,
                    source_type = excluded.source_type,
                    notes = excluded.notes""",
                (
                    record["permission_id"],
                    record["platform_id"],
                    record.get("registration_mark"),
                    record.get("operator_name"),
                    record["context_id"],
                    record.get("operational_area_id"),
                    record.get("scenario_id"),
                    record.get("flight_purpose"),
                    record.get("flight_type"),
                    serialize_utc(valid_from),
                    serialize_utc(valid_to),
                    record.get("altitude_ft_msl"),
                    record.get("departure_aerodrome"),
                    record.get("arrival_aerodrome"),
                    record["permission_status"],
                    serialize_utc(issued_at) if issued_at is not None else None,
                    record.get("source_type", "DEMO_MOCK"),
                    record.get("notes"),
                ),
            )

    async def find_by_platform_and_time(
        self, platform_id: str, observation_time_utc: datetime
    ) -> list[dict[str, Any]]:
        """Return rows whose stored validity interval contains the observation time."""
        instant = serialize_utc(observation_time_utc)
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """SELECT * FROM permissions
                WHERE platform_id = ? AND valid_from_utc <= ? AND valid_to_utc >= ?
                ORDER BY permission_id""",
                (platform_id, instant, instant),
            )
            rows = await cursor.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            mapped = dict(row)
            mapped["valid_from_utc"] = parse_utc(mapped["valid_from_utc"])
            mapped["valid_to_utc"] = parse_utc(mapped["valid_to_utc"])
            if mapped["issued_at_utc"] is not None:
                mapped["issued_at_utc"] = parse_utc(mapped["issued_at_utc"])
            result.append(mapped)
        return result

    async def find_by_platform_and_context(
        self, platform_id: str, context_id: str
    ) -> list[dict[str, Any]]:
        """Return all records for deterministic temporal classification."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """SELECT * FROM permissions
                WHERE platform_id = ? AND context_id = ?
                ORDER BY valid_from_utc, permission_id""",
                (platform_id, context_id),
            )
            rows = await cursor.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            mapped = dict(row)
            mapped["valid_from_utc"] = parse_utc(mapped["valid_from_utc"])
            mapped["valid_to_utc"] = parse_utc(mapped["valid_to_utc"])
            if mapped["issued_at_utc"] is not None:
                mapped["issued_at_utc"] = parse_utc(mapped["issued_at_utc"])
            result.append(mapped)
        return result
