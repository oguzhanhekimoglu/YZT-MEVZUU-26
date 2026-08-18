"""Validate the canonical platform registry and exact alias table."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from operational_decision.platform.platform_registry import (  # noqa: E402
    PlatformRegistryIndex,
    load_platform_aliases,
    load_platform_registry,
    normalize_platform_alias,
)

REGISTRY_PATH = PROJECT_ROOT / "data/platforms/platform_registry.json"
ALIASES_PATH = PROJECT_ROOT / "data/platforms/platform_aliases.json"


def main() -> int:
    """Validate schema, alias uniqueness, activity, and table completeness."""
    registry = load_platform_registry(REGISTRY_PATH)
    aliases = load_platform_aliases(ALIASES_PATH)
    index = PlatformRegistryIndex(registry, aliases)
    active = [record for record in registry.platforms if record.active]
    expected = {
        normalize_platform_alias(alias)
        for record in active
        for alias in (record.canonical_name, *record.aliases)
    }
    missing = sorted(expected.difference(aliases))
    if missing:
        raise ValueError(f"active registry aliases missing from alias table: {missing}")
    for alias, platform_id in aliases.items():
        match = index.find_exact_match(alias)
        if match is None or match.platform_id != platform_id:
            raise ValueError(f"alias does not resolve exactly: {alias}")
    print(f"Platform registry valid: {len(active)} active platforms, {len(aliases)} exact aliases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
