"""SQLite connection, migration, UTC, JSON, and sanitization primitives."""

import json
import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

MAX_SANITIZED_STRING_LENGTH = 1024
MAX_SANITIZED_PAYLOAD_BYTES = 65_536
SECRET_KEY_FRAGMENTS = ("password", "secret", "token", "api_key", "apikey")
WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def serialize_utc(value: datetime) -> str:
    """Serialize an aware datetime to canonical millisecond UTC with a Z suffix."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    utc_value = value.astimezone(UTC)
    if utc_value.microsecond % 1000:
        raise ValueError("datetime precision must not be finer than milliseconds")
    return utc_value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now() -> datetime:
    """Return current UTC time normalized to canonical millisecond precision."""
    value = datetime.now(UTC)
    return value.replace(microsecond=(value.microsecond // 1000) * 1000)


def parse_utc(value: str) -> datetime:
    """Parse a canonical Z-suffixed UTC timestamp."""
    if not value.endswith("Z"):
        raise ValueError("stored datetime must use the Z suffix")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if serialize_utc(parsed) != value:
        raise ValueError("stored datetime is not in canonical UTC format")
    return parsed


def encode_json(value: object) -> str:
    """Encode JSON deterministically for persistence."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def decode_json(value: str | None) -> object | None:
    """Decode a nullable persisted JSON value."""
    return None if value is None else json.loads(value)


def row_to_dict(row: aiosqlite.Row | None) -> dict[str, Any] | None:
    """Convert an optional SQLite row into a plain mapping."""
    return None if row is None else dict(row)


def _sanitize_value(value: object, *, key: str | None = None) -> object:
    """Recursively sanitize one raw audit value without inventing domain facts."""
    if key is not None and any(fragment in key.casefold() for fragment in SECRET_KEY_FRAGMENTS):
        return "[REDACTED]"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if WINDOWS_ABSOLUTE_PATH.match(value):
            return "[REDACTED_LOCAL_PATH]"
        return value[:MAX_SANITIZED_STRING_LENGTH]
    if isinstance(value, bytes):
        return f"[BINARY_REDACTED:{len(value)}_BYTES]"
    if isinstance(value, Mapping):
        return {
            str(item_key)[:100]: _sanitize_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [_sanitize_value(item) for item in value[:1000]]
    representation = repr(value)
    return representation[:MAX_SANITIZED_STRING_LENGTH]


def sanitize_raw_request(raw_request: object) -> str:
    """Return bounded, redacted JSON suitable for invalid-input auditing."""
    sanitized = _sanitize_value(raw_request)
    encoded = encode_json(sanitized)
    if len(encoded.encode("utf-8")) <= MAX_SANITIZED_PAYLOAD_BYTES:
        return encoded
    preview = encoded.encode("utf-8")[: MAX_SANITIZED_PAYLOAD_BYTES // 2]
    safe_preview = preview.decode("utf-8", errors="ignore")
    return encode_json(
        {
            "_sanitization": "PAYLOAD_TRUNCATED",
            "original_size_bytes": len(encoded.encode("utf-8")),
            "preview": safe_preview,
        }
    )


class SQLiteDatabase:
    """Manage one SQLite file with per-connection PRAGMAs and migrations."""

    def __init__(self, path: Path, migration_directory: Path) -> None:
        """Configure the database path and trusted SQL migration directory."""
        self.path = path
        self.migration_directory = migration_directory

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Open a row-mapped connection with required PRAGMAs."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(self.path, timeout=3.0)
        connection.row_factory = aiosqlite.Row
        try:
            await connection.execute("PRAGMA busy_timeout = 3000")
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("PRAGMA journal_mode = WAL")
            yield connection
        finally:
            await connection.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """Run an explicit immediate transaction and rollback on failure."""
        async with self.connection() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                await connection.rollback()
                raise
            else:
                await connection.commit()

    async def initialize(self) -> list[str]:
        """Apply each unapplied migration exactly once without deleting data."""
        applied_now: list[str] = []
        async with self.connection() as connection:
            await connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_name TEXT PRIMARY KEY,
                    applied_at_utc TEXT NOT NULL
                )"""
            )
            await connection.commit()
            cursor = await connection.execute("SELECT migration_name FROM schema_migrations")
            applied = {row[0] for row in await cursor.fetchall()}
            for migration_path in sorted(self.migration_directory.glob("*.sql")):
                if migration_path.name in applied:
                    continue
                sql = migration_path.read_text(encoding="utf-8")
                await connection.executescript(sql)
                await connection.execute(
                    "INSERT INTO schema_migrations (migration_name, applied_at_utc) VALUES (?, ?)",
                    (migration_path.name, serialize_utc(utc_now())),
                )
                await connection.commit()
                applied_now.append(migration_path.name)
        return applied_now

    async def list_tables(self) -> list[str]:
        """List non-internal tables for migration verification."""
        async with self.connection() as connection:
            cursor = await connection.execute(
                "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE ? ORDER BY name",
                ("table", "sqlite_%"),
            )
            return [row[0] for row in await cursor.fetchall()]
