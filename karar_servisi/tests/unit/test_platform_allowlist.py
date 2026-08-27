"""Integrity tests for the final canonical platform allowlist."""
# ruff: noqa: D103

from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

from operational_decision.platform.platform_registry import normalize_platform_alias

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = ROOT / "data/platforms/platform_allowlist.json"
REGISTRY_PATH = ROOT / "data/platforms/platform_registry.json"
ALIASES_PATH = ROOT / "data/platforms/platform_aliases.json"
ROUTES_PATH = ROOT / "data/seeds/raw_vlm_context_routes.json"
CONTEXTS_PATH = ROOT / "data/seeds/video_contexts.json"
PERMISSIONS_PATH = ROOT / "data/seeds/permissions.json"
FLIGHT_PLANS_PATH = ROOT / "data/seeds/flight_plans.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _allowlist_pairs(payload: dict[str, Any]) -> set[tuple[str, str]]:
    return {(item["platform_id"], item["canonical_name"]) for item in payload["platforms"]}


def _active_registry_pairs(payload: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (item["platform_id"], item["canonical_name"])
        for item in payload["platforms"]
        if item["active"] and item["platform_id"] != "PLT_INACTIVE_DEMO"
    }


def _registry_scope_errors(
    allowlist: dict[str, Any], registry: dict[str, Any]
) -> list[tuple[str, str]]:
    return sorted(_active_registry_pairs(registry) - _allowlist_pairs(allowlist))


def test_final_allowlist_schema_count_and_uniqueness() -> None:
    payload = _load(ALLOWLIST_PATH)
    assert set(payload) == {"schema_version", "description", "platforms"}
    assert payload["schema_version"] == "platform-allowlist/1.0"
    assert len(payload["platforms"]) == 112
    for item in payload["platforms"]:
        assert set(item) == {"platform_id", "canonical_name", "group"}
        assert all(isinstance(value, str) and value.strip() for value in item.values())

    platform_ids = [item["platform_id"] for item in payload["platforms"]]
    canonical_names = [item["canonical_name"].casefold() for item in payload["platforms"]]
    assert not [key for key, count in Counter(platform_ids).items() if count > 1]
    assert not [key for key, count in Counter(canonical_names).items() if count > 1]


def test_every_active_real_registry_record_is_allowlisted() -> None:
    assert _registry_scope_errors(_load(ALLOWLIST_PATH), _load(REGISTRY_PATH)) == []


def test_non_allowlisted_new_active_real_platform_is_rejected() -> None:
    registry = copy.deepcopy(_load(REGISTRY_PATH))
    candidate = copy.deepcopy(registry["platforms"][0])
    candidate.update(
        {
            "platform_id": "PLT_NOT_ON_FINAL_ALLOWLIST",
            "canonical_name": "Not On Final Allowlist",
            "aliases": ["Not On Final Allowlist"],
        }
    )
    registry["platforms"].append(candidate)
    assert _registry_scope_errors(_load(ALLOWLIST_PATH), registry) == [
        ("PLT_NOT_ON_FINAL_ALLOWLIST", "Not On Final Allowlist")
    ]


def test_alias_targets_are_existing_active_registry_records() -> None:
    registry = _load(REGISTRY_PATH)
    active_ids = {item["platform_id"] for item in registry["platforms"] if item["active"]}
    aliases = _load(ALIASES_PATH)["aliases"]
    assert all(item["platform_id"] in active_ids for item in aliases)


def test_routes_target_existing_platforms_and_active_contexts() -> None:
    registry = _load(REGISTRY_PATH)
    active_ids = {item["platform_id"] for item in registry["platforms"] if item["active"]}
    contexts = _load(CONTEXTS_PATH)
    active_video_ids = {item["video_id"] for item in contexts if item["status"] == "ACTIVE"}
    routes = _load(ROUTES_PATH)["routes"]
    assert set(routes) <= active_ids
    assert set(routes.values()) <= active_video_ids


def test_no_orphan_platform_context_permission_or_flight_plan_seed() -> None:
    registry = _load(REGISTRY_PATH)
    active_ids = {item["platform_id"] for item in registry["platforms"] if item["active"]}
    contexts = _load(CONTEXTS_PATH)
    context_ids = {item["context_id"] for item in contexts}
    for context in contexts:
        expected_id = context.get("expected_platform_id")
        assert expected_id is None or expected_id in active_ids

    for path in (PERMISSIONS_PATH, FLIGHT_PLANS_PATH):
        for item in _load(path):
            assert item["platform_id"] in active_ids
            assert item["context_id"] in context_ids


# NOT: PLT_KAAN, PLT_BAYRAKTAR_KIZILELMA, PLT_BAYRAKTAR_DIHA bu kümeden
# kaldırıldı — VRAG'ın tanıyabildiği tüm platformları kapsama kararıyla
# (Berra, ekip onayıyla) yeniden eklendiler. Kalan altısı (farklı platform_id
# biçimleriyle, ör. PLT_TUSAS_ANKA_III vs mevcut PLT_TUSAS_ANKA3) bu
# eklemeyle ilgisiz, önceki kaldırma kararları geçerliliğini koruyor.
REMOVED_PLATFORM_IDS = {
    "PLT_TUSAS_ANKA_III",
    "PLT_HURJET",
    "PLT_F15E",
    "PLT_F35_FAMILY",
    "PLT_BOEING_737",
    "PLT_AH64_APACHE",
}


def test_removed_platform_ids_have_no_registry_alias_route_or_seed_reference() -> None:
    registry = _load(REGISTRY_PATH)
    aliases = _load(ALIASES_PATH)["aliases"]
    routes = _load(ROUTES_PATH)["routes"]
    contexts = _load(CONTEXTS_PATH)
    permissions = _load(PERMISSIONS_PATH)
    flight_plans = _load(FLIGHT_PLANS_PATH)
    assert not ({item["platform_id"] for item in registry["platforms"]} & REMOVED_PLATFORM_IDS)
    assert not ({item["platform_id"] for item in aliases} & REMOVED_PLATFORM_IDS)
    assert not (set(routes) & REMOVED_PLATFORM_IDS)
    assert not ({item.get("expected_platform_id") for item in contexts} & REMOVED_PLATFORM_IDS)
    assert not ({item["platform_id"] for item in permissions} & REMOVED_PLATFORM_IDS)
    assert not ({item["platform_id"] for item in flight_plans} & REMOVED_PLATFORM_IDS)

def test_alias_rows_have_no_normalized_duplicates() -> None:
    aliases = _load(ALIASES_PATH)["aliases"]
    normalized = [normalize_platform_alias(item["alias"]) for item in aliases]
    assert not [key for key, count in Counter(normalized).items() if count > 1]

    registry = _load(REGISTRY_PATH)
    for platform in registry["platforms"]:
        values = [platform["canonical_name"], *platform["aliases"]]
        normalized_values = [normalize_platform_alias(value) for value in values]
        assert not [
            key for key, count in Counter(normalized_values).items() if count > 1
        ], platform["platform_id"]
