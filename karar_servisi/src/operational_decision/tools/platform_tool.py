"""Deterministic exact-alias platform tool."""

from operational_decision.contracts.common import PlatformStatus, VisualClass
from operational_decision.contracts.platform import (
    PlatformResult,
    PlatformToolRequest,
    UsageDomain,
)
from operational_decision.memory.event_service import EventService
from operational_decision.platform.platform_registry import (
    PlatformRegistryIndex,
    normalize_platform_alias,
    resolve_context_expectation,
)
from operational_decision.tools.base import BaseTool


class PlatformTool(BaseTool[PlatformToolRequest, PlatformResult]):
    """Resolve one active platform without fuzzy matching."""

    tool_name = "platform_tool"

    def __init__(
        self,
        registry: PlatformRegistryIndex,
        *,
        event_id: str,
        request_id: str,
        event_service: EventService | None = None,
    ) -> None:
        """Bind the tool to a prevalidated registry."""
        super().__init__(event_id=event_id, request_id=request_id, event_service=event_service)
        self.registry = registry

    async def execute_internal(self, request: PlatformToolRequest) -> PlatformResult:
        """Apply hypothesis-first then candidate-unique exact resolution."""
        if request.visual_class is VisualClass.NON_AIRCRAFT:
            return PlatformResult(platform_status=PlatformStatus.NON_AIRCRAFT)

        match = None
        matched_aliases: list[str] = []
        if request.final_visual_hypothesis:
            match = self.registry.find_exact_match(request.final_visual_hypothesis)
            if match is not None:
                matched_aliases.append(request.final_visual_hypothesis)

        if match is None:
            candidates = self.registry.resolve_candidates(request.candidate_names)
            if len(candidates) > 1:
                return PlatformResult(platform_status=PlatformStatus.AMBIGUOUS)
            if len(candidates) == 1:
                match = candidates[0]
                matched_aliases = [
                    candidate
                    for candidate in request.candidate_names
                    if (resolved := self.registry.find_exact_match(candidate)) is not None
                    and resolved.platform_id == match.platform_id
                ]

        if match is None:
            return PlatformResult(platform_status=PlatformStatus.UNKNOWN)

        status = resolve_context_expectation(match, request.context_id, request.context_status)
        return PlatformResult(
            platform_status=status,
            usage_domain=(match.taxonomy.usage_domain if match.taxonomy else UsageDomain.UNKNOWN),
            platform_id=match.platform_id,
            matched_platform=match.canonical_name,
            canonical_name=match.canonical_name,
            category=match.category,
            taxonomy=match.taxonomy,
            matched_aliases=sorted(set(matched_aliases), key=normalize_platform_alias),
            platform_origin=match.platform_origin,
            manufacturer_country_code=match.manufacturer_country_code,
            identity_scope=(match.taxonomy.identity_scope if match.taxonomy else None),
            variant_policy=(match.taxonomy.variant_policy if match.taxonomy else None),
        )
