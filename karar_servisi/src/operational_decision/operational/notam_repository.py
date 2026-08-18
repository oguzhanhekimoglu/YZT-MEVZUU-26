"""Persistence-only NOTAM repository."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from operational_decision.operational.database import OperationalDatabase
from operational_decision.persistence.sqlite_database import (
    decode_json,
    encode_json,
    parse_utc,
    serialize_utc,
)


class NotamRepository:
    """Store and query NOTAM rows without calculating relevance."""

    def __init__(self, database: OperationalDatabase) -> None:
        """Bind the repository to an operational database."""
        self.database = database

    async def upsert(self, record: Mapping[str, object]) -> None:
        """Insert or update one NOTAM using fixed parameterized SQL."""
        valid_from = record["valid_from_utc"]
        valid_to = record["valid_to_utc"]
        if not isinstance(valid_from, datetime) or not isinstance(valid_to, datetime):
            raise TypeError("NOTAM validity fields must be datetime values")
        async with self.database.transaction() as connection:
            await connection.execute(
                """INSERT INTO notams (
                    notam_id, series, notam_number, context_id, operational_area_id,
                    valid_from_utc, valid_to_utc, notam_status, restriction_type,
                    operation_effect, relevance_tags_json, affected_platform_categories_json,
                    affected_platform_ids_json, summary_tr, source_reference, scenario_id,
                    source_type, display_number, notam_year, q_code, item_e,
                    estimated_end, permanent, lower_limit, upper_limit, fir_code,
                    aerodrome_code, operational_reason_tr, conflict_with_permission,
                    conflict_with_flight_plan
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(notam_id) DO UPDATE SET
                    series = excluded.series,
                    notam_number = excluded.notam_number,
                    context_id = excluded.context_id,
                    operational_area_id = excluded.operational_area_id,
                    valid_from_utc = excluded.valid_from_utc,
                    valid_to_utc = excluded.valid_to_utc,
                    notam_status = excluded.notam_status,
                    restriction_type = excluded.restriction_type,
                    operation_effect = excluded.operation_effect,
                    relevance_tags_json = excluded.relevance_tags_json,
                    affected_platform_categories_json = excluded.affected_platform_categories_json,
                    affected_platform_ids_json = excluded.affected_platform_ids_json,
                    summary_tr = excluded.summary_tr,
                    source_reference = excluded.source_reference,
                    scenario_id = excluded.scenario_id,
                    source_type = excluded.source_type,
                    display_number = excluded.display_number,
                    notam_year = excluded.notam_year,
                    q_code = excluded.q_code,
                    item_e = excluded.item_e,
                    estimated_end = excluded.estimated_end,
                    permanent = excluded.permanent,
                    lower_limit = excluded.lower_limit,
                    upper_limit = excluded.upper_limit,
                    fir_code = excluded.fir_code,
                    aerodrome_code = excluded.aerodrome_code,
                    operational_reason_tr = excluded.operational_reason_tr,
                    conflict_with_permission = excluded.conflict_with_permission,
                    conflict_with_flight_plan = excluded.conflict_with_flight_plan""",
                (
                    record["notam_id"],
                    record.get("series"),
                    record.get("number", record.get("notam_number")),
                    record.get("context_id"),
                    record["operational_area_id"],
                    serialize_utc(valid_from),
                    serialize_utc(valid_to),
                    record["notam_status"],
                    record.get("restriction_type"),
                    record["operation_effect"],
                    encode_json(record.get("relevance_tags", [])),
                    encode_json(record.get("affected_platform_categories", [])),
                    encode_json(record.get("affected_platform_ids", [])),
                    record["summary_tr"],
                    record.get("source_reference"),
                    record.get("scenario_id"),
                    record.get("source_type", "DEMO_MOCK"),
                    record.get("display_number"),
                    record.get("year"),
                    record.get("q_code"),
                    record.get("item_e"),
                    int(bool(record.get("estimated_end", False))),
                    int(bool(record.get("permanent", False))),
                    record.get("lower_limit"),
                    record.get("upper_limit"),
                    record.get("fir_code"),
                    record.get("aerodrome_code"),
                    record.get("operational_reason_tr"),
                    int(bool(record.get("conflict_with_permission", False))),
                    int(bool(record.get("conflict_with_flight_plan", False))),
                ),
            )

    @staticmethod
    def _map_row(row: Any) -> dict[str, Any]:
        mapped: dict[str, Any] = dict(row)
        mapped["valid_from_utc"] = parse_utc(mapped["valid_from_utc"])
        mapped["valid_to_utc"] = parse_utc(mapped["valid_to_utc"])
        mapped["relevance_tags"] = decode_json(mapped.pop("relevance_tags_json")) or []
        mapped["affected_platform_categories"] = (
            decode_json(mapped.pop("affected_platform_categories_json")) or []
        )
        mapped["affected_platform_ids"] = (
            decode_json(mapped.pop("affected_platform_ids_json")) or []
        )
        mapped["number"] = int(mapped["notam_number"]) if mapped.get("notam_number") else None
        mapped["year"] = mapped.pop("notam_year")
        mapped["estimated_end"] = bool(mapped["estimated_end"])
        mapped["permanent"] = bool(mapped["permanent"])
        mapped["conflict_with_permission"] = bool(mapped["conflict_with_permission"])
        mapped["conflict_with_flight_plan"] = bool(mapped["conflict_with_flight_plan"])
        return mapped

    async def find_by_area_and_time(
        self, operational_area_id: str, observation_time_utc: datetime
    ) -> list[dict[str, Any]]:
        """Return NOTAM rows by area and stored interval without relevance logic."""
        instant = serialize_utc(observation_time_utc)
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """SELECT * FROM notams
                WHERE operational_area_id = ? AND valid_from_utc <= ? AND valid_to_utc >= ?
                ORDER BY notam_id""",
                (operational_area_id, instant, instant),
            )
            rows = await cursor.fetchall()
        return [self._map_row(row) for row in rows]

    async def find_by_area(self, operational_area_id: str) -> list[dict[str, Any]]:
        """Return all area records so past and future states remain observable."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """SELECT * FROM notams WHERE operational_area_id = ?
                ORDER BY valid_from_utc, notam_id""",
                (operational_area_id,),
            )
            rows = await cursor.fetchall()
        return [self._map_row(row) for row in rows]
