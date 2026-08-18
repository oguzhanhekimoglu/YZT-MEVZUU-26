"""Turkey Inventory V1 registry loader and integrity tests."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from operational_decision.inventory.turkey_inventory_registry import (
    TurkeyInventoryRegistryError,
    load_turkey_inventory_registry,
)

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "data/inventory/turkey_inventory.json"
PLATFORM_PATH = ROOT / "data/platforms/platform_registry.json"


def inventory_payload() -> dict[str, object]:
    """Return an isolated valid registry payload."""
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def platform_payload() -> dict[str, object]:
    """Return an isolated valid platform payload."""
    return json.loads(PLATFORM_PATH.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, object]) -> Path:
    """Write one temporary JSON fixture."""
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_registry_loads_and_preserves_metadata() -> None:
    """Valid DEMO_MOCK data loads with exact metadata and records."""
    registry = load_turkey_inventory_registry(INVENTORY_PATH, PLATFORM_PATH)
    assert registry.dataset.dataset_id == "TR-INVENTORY-DEMO"
    assert registry.dataset.dataset_version == "1.0.0"
    assert registry.find_active("PLT_F16") is not None
    assert registry.find_active("F-16") is None
    assert registry.find_active("PLT_INACTIVE_DEMO") is None


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_record", "duplicate inventory_record_id"),
        ("duplicate_platform", "duplicate active inventory platform_id"),
        ("unknown_platform", "unknown platform_id"),
        ("inactive_platform", "inactive platform"),
    ],
)
def test_registry_integrity_failures(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    """Duplicate and cross-registry integrity violations are explicit errors."""
    payload = inventory_payload()
    records = payload["records"]
    assert isinstance(records, list)
    if mutation == "duplicate_record":
        records.append(deepcopy(records[0]))
    elif mutation == "duplicate_platform":
        duplicate = deepcopy(records[0])
        duplicate["inventory_record_id"] = "TR-DEMO-DUPLICATE"
        records.append(duplicate)
    elif mutation == "unknown_platform":
        records[0]["platform_id"] = "PLT_UNKNOWN"
    else:
        records[0]["platform_id"] = "PLT_INACTIVE_DEMO"

    path = write_json(tmp_path / "inventory.json", payload)
    with pytest.raises(TurkeyInventoryRegistryError, match=message):
        load_turkey_inventory_registry(path, PLATFORM_PATH)
