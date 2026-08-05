"""Strict loader and exact platform-id index for Turkey Inventory V1."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from operational_decision.contracts.inventory import (
    TurkeyInventoryDataset,
    TurkeyInventoryRecord,
)
from operational_decision.contracts.platform import PlatformRegistry
from operational_decision.platform.platform_registry import load_platform_registry


class TurkeyInventoryRegistryError(ValueError):
    """Report explicit Inventory registry load or integrity failures."""


class TurkeyInventoryRegistry:
    """Preserve dataset metadata and provide exact active platform-id lookup."""

    def __init__(
        self,
        dataset: TurkeyInventoryDataset,
        platform_registry: PlatformRegistry,
    ) -> None:
        """Validate cross-registry integrity and build an exact lookup index."""
        self.dataset = dataset
        platforms = {record.platform_id: record for record in platform_registry.platforms}
        record_ids: set[str] = set()
        active_platform_ids: set[str] = set()
        active_records: dict[str, TurkeyInventoryRecord] = {}

        for record in dataset.records:
            if record.inventory_record_id in record_ids:
                raise TurkeyInventoryRegistryError(
                    f"duplicate inventory_record_id: {record.inventory_record_id}"
                )
            record_ids.add(record.inventory_record_id)

            platform = platforms.get(record.platform_id)
            if platform is None:
                raise TurkeyInventoryRegistryError(
                    f"inventory references unknown platform_id: {record.platform_id}"
                )
            if record.active and not platform.active:
                raise TurkeyInventoryRegistryError(
                    f"active inventory record references inactive platform: {record.platform_id}"
                )
            if record.active:
                if record.platform_id in active_platform_ids:
                    raise TurkeyInventoryRegistryError(
                        f"duplicate active inventory platform_id: {record.platform_id}"
                    )
                active_platform_ids.add(record.platform_id)
                active_records[record.platform_id] = record

        self._active_records = active_records

    def find_active(self, platform_id: str) -> TurkeyInventoryRecord | None:
        """Return an exact active record; aliases and fuzzy matching are unsupported."""
        return self._active_records.get(platform_id)


def load_turkey_inventory_registry(
    inventory_path: Path,
    platform_registry: PlatformRegistry | Path,
) -> TurkeyInventoryRegistry:
    """Strictly load Inventory JSON and validate it against Platform Registry."""
    try:
        raw = inventory_path.read_text(encoding="utf-8-sig")
        dataset = TurkeyInventoryDataset.model_validate_json(raw, strict=True)
        platforms = (
            load_platform_registry(platform_registry)
            if isinstance(platform_registry, Path)
            else platform_registry
        )
        return TurkeyInventoryRegistry(dataset, platforms)
    except TurkeyInventoryRegistryError:
        raise
    except (OSError, ValueError, ValidationError) as error:
        raise TurkeyInventoryRegistryError(
            f"failed to load Turkey Inventory registry: {type(error).__name__}"
        ) from error
