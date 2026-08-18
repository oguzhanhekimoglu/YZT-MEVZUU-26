"""Platform registry and resolution contracts."""

import re
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator

from operational_decision.contracts.common import (
    ContextStatus,
    PlatformStatus,
    StrictContract,
    VisualClass,
)


class PlatformOrigin(StrEnum):
    """Controlled model-origin classifications for registry records."""

    DOMESTIC_ORIGIN = "DOMESTIC_ORIGIN"
    FOREIGN_ORIGIN = "FOREIGN_ORIGIN"
    MULTINATIONAL_ORIGIN = "MULTINATIONAL_ORIGIN"
    UNKNOWN = "UNKNOWN"


class BaseCategory(StrEnum):
    """Stable physical platform categories used only as registry metadata."""

    FIXED_WING_AIRCRAFT = "FIXED_WING_AIRCRAFT"
    ROTARY_WING_AIRCRAFT = "ROTARY_WING_AIRCRAFT"
    MULTIROTOR_AIRCRAFT = "MULTIROTOR_AIRCRAFT"
    TILTROTOR_AIRCRAFT = "TILTROTOR_AIRCRAFT"
    LOITERING_MUNITION = "LOITERING_MUNITION"


class UsageDomain(StrEnum):
    """Controlled platform usage domains used only as registry metadata."""

    MILITARY = "MILITARY"
    CIVIL = "CIVIL"
    DUAL_USE = "DUAL_USE"
    DEMO = "DEMO"
    UNKNOWN = "UNKNOWN"


class IdentityScope(StrEnum):
    """Identity granularity represented by one registry record."""

    MODEL = "MODEL"
    MODEL_FAMILY = "MODEL_FAMILY"
    VARIANT = "VARIANT"
    GENERIC_CLASS = "GENERIC_CLASS"


class VariantPolicy(StrEnum):
    """Metadata describing how platform variants should be represented."""

    METADATA_ONLY = "METADATA_ONLY"
    EXPLICIT_CHILD_RECORDS = "EXPLICIT_CHILD_RECORDS"
    EXACT_IDENTITY = "EXACT_IDENTITY"
    GENERIC_ONLY = "GENERIC_ONLY"


CONTROLLED_TAXONOMY_VALUE_PATTERN = r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$"


class PlatformTaxonomy(StrictContract):
    """Optional descriptive taxonomy that does not affect runtime policy."""

    base_category: BaseCategory
    usage_domain: UsageDomain
    primary_role: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=CONTROLLED_TAXONOMY_VALUE_PATTERN,
    )
    operational_class: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=CONTROLLED_TAXONOMY_VALUE_PATTERN,
    )
    traits: list[str] = Field(default_factory=list)
    identity_scope: IdentityScope
    variant_policy: VariantPolicy

    @field_validator("traits")
    @classmethod
    def _validate_traits(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("taxonomy traits must not contain duplicates")
        if any(not re.fullmatch(CONTROLLED_TAXONOMY_VALUE_PATTERN, value) for value in values):
            raise ValueError("taxonomy traits must be controlled uppercase values")
        return values


class PlatformRecord(StrictContract):
    """One exact-matchable platform registry record."""

    platform_id: str = Field(min_length=1, max_length=150)
    canonical_name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(min_length=1)
    category: VisualClass
    platform_origin: PlatformOrigin
    manufacturer_country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    taxonomy: PlatformTaxonomy | None = None
    default_expectation: PlatformStatus
    context_overrides: dict[str, PlatformStatus] = Field(default_factory=dict)
    active: bool
    source_type: str = Field(min_length=1, max_length=50)


class PlatformRegistry(StrictContract):
    """Validated collection of platform records."""

    schema_version: Literal["platform-registry/1.1"]
    platforms: list[PlatformRecord]


class PlatformToolRequest(StrictContract):
    """Input facts used for exact platform resolution."""

    visual_class: VisualClass
    final_visual_hypothesis: str | None = Field(default=None, max_length=200)
    candidate_names: list[str] = Field(default_factory=list)
    context_id: str | None = Field(default=None, max_length=150)
    context_status: ContextStatus = ContextStatus.MISSING


class PlatformResult(StrictContract):
    """Domain result of exact platform registry resolution."""

    platform_status: PlatformStatus
    usage_domain: UsageDomain = UsageDomain.UNKNOWN
    platform_id: str | None = Field(default=None, max_length=150)
    matched_platform: str | None = Field(default=None, max_length=200)
    canonical_name: str | None = Field(default=None, max_length=200)
    category: VisualClass | None = None
    taxonomy: PlatformTaxonomy | None = None
    matched_aliases: list[str] = Field(default_factory=list)
    platform_origin: PlatformOrigin | None = None
    manufacturer_country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    identity_scope: IdentityScope | None = None
    variant_policy: VariantPolicy | None = None
