"""Abstract interface for the one allowed local LLM transport."""

from abc import ABC, abstractmethod
from collections.abc import Sequence


class LocalLLMError(RuntimeError):
    """Sanitized local model transport or response error."""


class BaseLLMClient(ABC):
    """Asynchronous local structured-output client interface."""

    @abstractmethod
    async def generate(self, messages: Sequence[dict[str, str]]) -> str:
        """Return one raw assistant response without transport retries."""

    @abstractmethod
    async def unload(self) -> None:
        """Explicitly release the configured local model."""
