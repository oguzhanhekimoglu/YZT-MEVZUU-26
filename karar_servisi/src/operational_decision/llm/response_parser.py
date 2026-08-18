"""Strict local LLM JSON parsing with one schema-repair attempt."""

from pydantic import ValidationError

from operational_decision.contracts.llm import LLMDecision, LLMEvidencePackage
from operational_decision.llm.base_client import BaseLLMClient, LocalLLMError
from operational_decision.llm.prompt_builder import PromptBuilder


class LLMResponseParseError(ValueError):
    """Sanitized JSON or schema validation failure."""


class LLMRunResult:
    """Auditable outcome of initial generation and at most one repair."""

    def __init__(
        self,
        decision: LLMDecision | None,
        *,
        repair_attempted: bool,
        fallback_required: bool,
        errors: list[str],
    ) -> None:
        """Store generation outcome and audit indicators."""
        self.decision = decision
        self.repair_attempted = repair_attempted
        self.fallback_required = fallback_required
        self.errors = errors


def parse_llm_decision(raw: str) -> LLMDecision:
    """Parse only a strict LLMDecision JSON object."""
    try:
        return LLMDecision.model_validate_json(raw, strict=True)
    except (ValidationError, ValueError) as exc:
        raise LLMResponseParseError("response is not valid LLMDecision JSON") from exc


class StructuredDecisionRunner:
    """Run one generation and one parse/schema repair, never transport retry."""

    def __init__(self, client: BaseLLMClient, prompt_builder: PromptBuilder | None = None) -> None:
        """Configure the one local client and deterministic prompt builder."""
        self._client = client
        self._prompt_builder = prompt_builder or PromptBuilder()

    async def run(self, evidence: LLMEvidencePackage) -> LLMRunResult:
        """Return fallback_required on transport failure or two invalid responses."""
        messages = self._prompt_builder.build(evidence)
        try:
            raw = await self._client.generate(messages)
        except LocalLLMError as exc:
            return LLMRunResult(
                None, repair_attempted=False, fallback_required=True, errors=[str(exc)]
            )
        try:
            return LLMRunResult(
                parse_llm_decision(raw),
                repair_attempted=False,
                fallback_required=False,
                errors=[],
            )
        except LLMResponseParseError as first_error:
            repair_messages = self._prompt_builder.build_repair(messages, raw, str(first_error))
            try:
                repaired = await self._client.generate(repair_messages)
            except LocalLLMError as exc:
                return LLMRunResult(
                    None,
                    repair_attempted=True,
                    fallback_required=True,
                    errors=[str(first_error), str(exc)],
                )
            try:
                decision = parse_llm_decision(repaired)
            except LLMResponseParseError as second_error:
                return LLMRunResult(
                    None,
                    repair_attempted=True,
                    fallback_required=True,
                    errors=[str(first_error), str(second_error)],
                )
            return LLMRunResult(
                decision,
                repair_attempted=True,
                fallback_required=False,
                errors=[str(first_error)],
            )
