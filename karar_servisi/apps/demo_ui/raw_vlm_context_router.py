"""Deterministic platform → demo context routing for automated Ham VLM analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[2]
ROUTE_MAPPING_PATH = ROOT / "data/seeds/raw_vlm_context_routes.json"
VIDEO_CONTEXTS_PATH = ROOT / "data/seeds/video_contexts.json"


def _load_route_config(path: Path = ROUTE_MAPPING_PATH) -> dict[str, Any]:
    """Load and validate the raw VLM context route configuration."""
    content = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(content, dict)
        or content.get("schema_version") != "raw-vlm-context-routes/1.0"
    ):
        raise ValueError("unsupported raw VLM context route schema")
    routes = content.get("routes")
    if not isinstance(routes, dict):
        raise ValueError("routes must be an object")
    return content


def load_raw_vlm_context_routes(path: Path = ROUTE_MAPPING_PATH) -> dict[str, str]:
    """Return the platform_id → video_id route mapping."""
    config = _load_route_config(path)
    routes = config["routes"]
    return {str(k): str(v) for k, v in routes.items()}


def raw_vlm_fallback_video_id(path: Path = ROUTE_MAPPING_PATH) -> str:
    """Return the fallback video_id for unresolved platforms."""
    config = _load_route_config(path)
    fallback = config.get("fallback_video_id")
    if not isinstance(fallback, str) or not fallback.strip():
        return "VIDEO_RAW_VLM_DEFAULT"
    return fallback


def resolve_raw_vlm_video_id(
    platform_id: str | None,
    *,
    route_path: Path = ROUTE_MAPPING_PATH,
) -> tuple[str, bool]:
    """Resolve a video_id for the given platform_id.

    Returns:
        Tuple of (video_id, is_fallback). is_fallback is True when the
        platform could not be matched to a specific demo context.

    """
    if platform_id is None:
        return raw_vlm_fallback_video_id(route_path), True
    routes = load_raw_vlm_context_routes(route_path)
    video_id = routes.get(platform_id)
    if video_id is not None:
        return video_id, False
    return raw_vlm_fallback_video_id(route_path), True


def resolve_raw_vlm_runtime_context(
    *,
    runtime_mode: Literal["DEMO", "PRODUCTION"],
    platform_id: str | None,
    demo_track_id: str | None = None,
    upstream_video_id: str | None = None,
    upstream_track_id: str | None = None,
    first_seen_offset_seconds: float | None = None,
    last_seen_offset_seconds: float | None = None,
    route_path: Path = ROUTE_MAPPING_PATH,
) -> tuple[dict[str, str | float], bool]:
    """Resolve demo context or preserve an explicit production tracking envelope."""
    if runtime_mode == "DEMO":
        video_id, is_fallback = resolve_raw_vlm_video_id(
            platform_id,
            route_path=route_path,
        )
        if demo_track_id is None or not demo_track_id.strip():
            raise ValueError("DEMO_TRACK_ID_MISSING")
        return (
            {
                "video_id": video_id,
                "track_id": demo_track_id,
                "first_seen_offset_seconds": 0.0,
                "last_seen_offset_seconds": 1.0,
            },
            is_fallback,
        )

    missing = [
        name
        for name, value in (
            ("video_id", upstream_video_id),
            ("track_id", upstream_track_id),
            ("first_seen_offset_seconds", first_seen_offset_seconds),
            ("last_seen_offset_seconds", last_seen_offset_seconds),
        )
        if value is None or isinstance(value, str) and not value.strip()
    ]
    if missing:
        raise ValueError("CONTEXT_MISSING: " + ", ".join(missing))
    assert upstream_video_id is not None
    assert upstream_track_id is not None
    assert first_seen_offset_seconds is not None
    assert last_seen_offset_seconds is not None
    if first_seen_offset_seconds < 0 or last_seen_offset_seconds < first_seen_offset_seconds:
        raise ValueError("CONTEXT_INVALID: observation interval")
    return (
        {
            "video_id": upstream_video_id,
            "track_id": upstream_track_id,
            "first_seen_offset_seconds": first_seen_offset_seconds,
            "last_seen_offset_seconds": last_seen_offset_seconds,
        },
        False,
    )


def resolve_raw_vlm_visual_confidence(
    *,
    runtime_mode: Literal["DEMO", "PRODUCTION"],
    upstream_visual_confidence: float | None,
) -> float:
    """Use a demo default only in DEMO; require an explicit production value."""
    if upstream_visual_confidence is None:
        if runtime_mode == "DEMO":
            return 0.50
        raise ValueError("VISUAL_CONFIDENCE_MISSING")
    if not 0.0 <= upstream_visual_confidence <= 1.0:
        raise ValueError("VISUAL_CONFIDENCE_INVALID")
    return upstream_visual_confidence


def validate_route_mapping(
    route_path: Path = ROUTE_MAPPING_PATH,
    contexts_path: Path = VIDEO_CONTEXTS_PATH,
) -> list[str]:
    """Validate that all route mapping video_ids exist and are ACTIVE.

    Returns a list of validation error messages (empty means valid).
    """
    routes = load_raw_vlm_context_routes(route_path)
    fallback = raw_vlm_fallback_video_id(route_path)
    all_video_ids = set(routes.values()) | {fallback}

    contexts = json.loads(contexts_path.read_text(encoding="utf-8"))
    active_ids = {
        item["video_id"]
        for item in contexts
        if isinstance(item, dict) and item.get("status") == "ACTIVE"
    }
    errors: list[str] = []
    for video_id in sorted(all_video_ids):
        if video_id not in active_ids:
            errors.append(f"route references non-existent or inactive video_id: {video_id}")
    seen: set[str] = set()
    for _platform_id, video_id in routes.items():
        if video_id in seen:
            continue
        seen.add(video_id)
    return errors
