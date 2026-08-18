"""Persistence-only video context repository."""

from operational_decision.contracts.context import VideoContextRecord
from operational_decision.operational.database import OperationalDatabase
from operational_decision.persistence.sqlite_database import parse_utc, serialize_utc


class ContextRepository:
    """Store and retrieve video context records without resolving context."""

    def __init__(self, database: OperationalDatabase) -> None:
        """Bind the repository to an operational database."""
        self.database = database

    async def upsert(self, record: VideoContextRecord) -> None:
        """Insert or update one context by its stable video identifier."""
        async with self.database.transaction() as connection:
            await connection.execute(
                """INSERT INTO video_contexts (
                    video_id, camera_id, context_id, operational_area_id, scenario_id,
                    expected_platform_id,
                    video_start_time_utc, description, fir_code, aerodrome_code,
                    operation_lower_limit, operation_upper_limit,
                    environment, status, source_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    camera_id = excluded.camera_id,
                    context_id = excluded.context_id,
                    operational_area_id = excluded.operational_area_id,
                    scenario_id = excluded.scenario_id,
                    expected_platform_id = excluded.expected_platform_id,
                    video_start_time_utc = excluded.video_start_time_utc,
                    description = excluded.description,
                    fir_code = excluded.fir_code,
                    aerodrome_code = excluded.aerodrome_code,
                    operation_lower_limit = excluded.operation_lower_limit,
                    operation_upper_limit = excluded.operation_upper_limit,
                    environment = excluded.environment,
                    status = excluded.status,
                    source_type = excluded.source_type""",
                (
                    record.video_id,
                    record.camera_id,
                    record.context_id,
                    record.operational_area_id,
                    record.scenario_id,
                    record.expected_platform_id,
                    serialize_utc(record.video_start_time_utc),
                    record.description,
                    record.fir_code,
                    record.aerodrome_code,
                    record.operation_lower_limit,
                    record.operation_upper_limit,
                    record.environment,
                    record.status,
                    record.source_type,
                ),
            )

    async def get_video_context(self, video_id: str) -> VideoContextRecord | None:
        """Return one context or None without manufacturing a fallback record."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM video_contexts WHERE video_id = ?", (video_id,)
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return VideoContextRecord(
            video_id=row["video_id"],
            camera_id=row["camera_id"],
            context_id=row["context_id"],
            operational_area_id=row["operational_area_id"],
            scenario_id=row["scenario_id"],
            expected_platform_id=row["expected_platform_id"],
            video_start_time_utc=parse_utc(row["video_start_time_utc"]),
            description=row["description"],
            fir_code=row["fir_code"],
            aerodrome_code=row["aerodrome_code"],
            operation_lower_limit=row["operation_lower_limit"],
            operation_upper_limit=row["operation_upper_limit"],
            environment=row["environment"],
            status=row["status"],
            source_type=row["source_type"],
        )
