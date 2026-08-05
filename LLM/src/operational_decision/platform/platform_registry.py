"""Load and query the canonical exact-match platform registry."""

import json
import unicodedata
from collections.abc import Iterable
from pathlib import Path

from operational_decision.contracts.common import ContextStatus, PlatformStatus, VisualClass
from operational_decision.contracts.platform import (
    BaseCategory,
    IdentityScope,
    PlatformOrigin,
    PlatformRecord,
    PlatformRegistry,
    UsageDomain,
    VariantPolicy,
)


def normalize_platform_alias(value: str) -> str:
    """Apply deterministic text normalization without fuzzy matching."""
    return " ".join(unicodedata.normalize("NFKC", value).strip().casefold().split())


def load_platform_registry(path: Path) -> PlatformRegistry:
    """Load and strictly validate the platform registry JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("platforms"), list):
        raise ValueError("platform registry must contain a platforms list")
    if payload.get("schema_version") != "platform-registry/1.1":
        raise ValueError("unsupported platform registry schema_version")
    records: list[PlatformRecord] = []
    for item in payload["platforms"]:
        if not isinstance(item, dict):
            raise ValueError("each platform must be an object")
        converted = dict(item)
        converted["category"] = VisualClass(converted["category"])
        converted["platform_origin"] = PlatformOrigin(converted["platform_origin"])
        converted["default_expectation"] = PlatformStatus(converted["default_expectation"])
        taxonomy = converted.get("taxonomy")
        if taxonomy is not None:
            if not isinstance(taxonomy, dict):
                raise ValueError("taxonomy must be an object")
            converted_taxonomy = dict(taxonomy)
            converted_taxonomy["base_category"] = BaseCategory(
                converted_taxonomy["base_category"]
            )
            converted_taxonomy["usage_domain"] = UsageDomain(
                converted_taxonomy["usage_domain"]
            )
            converted_taxonomy["identity_scope"] = IdentityScope(
                converted_taxonomy["identity_scope"]
            )
            converted_taxonomy["variant_policy"] = VariantPolicy(
                converted_taxonomy["variant_policy"]
            )
            converted["taxonomy"] = converted_taxonomy
        overrides = converted.get("context_overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError("context_overrides must be an object")
        converted["context_overrides"] = {
            str(key): PlatformStatus(value) for key, value in overrides.items()
        }
        records.append(PlatformRecord.model_validate(converted))
    registry = PlatformRegistry(schema_version="platform-registry/1.1", platforms=records)
    platform_ids: set[str] = set()
    canonical_names: set[str] = set()
    for record in registry.platforms:
        if record.platform_id in platform_ids:
            raise ValueError(f"duplicate platform_id: {record.platform_id}")
        platform_ids.add(record.platform_id)
        normalized_name = normalize_platform_alias(record.canonical_name)
        if normalized_name in canonical_names:
            raise ValueError(f"duplicate canonical_name: {record.canonical_name}")
        canonical_names.add(normalized_name)
    PlatformRegistryIndex(registry)
    return registry


def load_platform_aliases(path: Path) -> dict[str, str]:
    """Load the explicit alias table and reject normalized duplicates."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("aliases")
    if not isinstance(entries, list):
        raise ValueError("platform alias file must contain an aliases list")
    aliases: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each alias entry must be an object")
        alias = entry.get("alias")
        platform_id = entry.get("platform_id")
        if not isinstance(alias, str) or not isinstance(platform_id, str):
            raise ValueError("alias and platform_id must be strings")
        normalized = normalize_platform_alias(alias)
        existing = aliases.get(normalized)
        if existing is not None and existing != platform_id:
            raise ValueError(f"alias maps to multiple platforms: {alias}")
        aliases[normalized] = platform_id
    return aliases


class PlatformRegistryIndex:
    """Index active platform aliases for exact deterministic resolution."""

    def __init__(
        self,
        registry: PlatformRegistry,
        explicit_aliases: dict[str, str] | None = None,
    ) -> None:
        """Build an index while rejecting cross-platform alias collisions."""
        self.registry = registry
        self._platforms = {
            platform.platform_id: platform for platform in registry.platforms if platform.active
        }
        self._aliases: dict[str, PlatformRecord] = {}
        for platform in self._platforms.values():
            for alias in (platform.canonical_name, *platform.aliases):
                self._add_alias(alias, platform)
        for alias, platform_id in (explicit_aliases or {}).items():
            explicit_platform = self._platforms.get(platform_id)
            if explicit_platform is None:
                raise ValueError(f"alias references inactive or unknown platform: {platform_id}")
            self._add_alias(alias, explicit_platform)

    def _add_alias(self, alias: str, platform: PlatformRecord) -> None:
        normalized = normalize_platform_alias(alias)
        if not normalized:
            raise ValueError(f"empty alias for platform {platform.platform_id}")
        existing = self._aliases.get(normalized)
        if existing is not None and existing.platform_id != platform.platform_id:
            raise ValueError(f"alias maps to multiple platforms: {alias}")
        self._aliases[normalized] = platform

    def find_exact_match(self, value: str) -> PlatformRecord | None:
        """Return one active exact normalized alias match."""
        return self._aliases.get(normalize_platform_alias(value))

    def resolve_candidates(self, candidates: Iterable[str]) -> list[PlatformRecord]:
        """Return unique active records exactly matched by candidates."""
        matches: dict[str, PlatformRecord] = {}
        for candidate in candidates:
            match = self.find_exact_match(candidate)
            if match is not None:
                matches[match.platform_id] = match
        return [matches[key] for key in sorted(matches)]


def find_exact_match(value: str, registry: PlatformRegistryIndex) -> PlatformRecord | None:
    """Functional exact-match facade."""
    return registry.find_exact_match(value)


def resolve_candidates(
    candidates: list[str], registry: PlatformRegistryIndex
) -> list[PlatformRecord]:
    """Functional candidate-resolution facade."""
    return registry.resolve_candidates(candidates)


def resolve_context_expectation(
    platform: PlatformRecord,
    context_id: str | None,
    context_status: ContextStatus = ContextStatus.COMPLETE,
) -> PlatformStatus:
    """Resolve expectation only when context is complete and identified."""
    if context_status is not ContextStatus.COMPLETE or context_id is None:
        return PlatformStatus.UNKNOWN
    return platform.context_overrides.get(context_id, platform.default_expectation)
