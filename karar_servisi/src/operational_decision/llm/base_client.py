"""Abstract interface for the one allowed local LLM transport."""

from abc import ABC, abstractmethod
from collections.abc import Sequence


class LocalLLMError(RuntimeError):
    """Sanitized local model transport or response error."""


class BaseLLMClient(ABC):
    """Asynchronous local structured-output client interface."""

    @abstractmethod
    async def generate(
        self,
        messages: Sequence[dict[str, str]],
        *,
        response_schema: dict[str, object] | None = None,
        max_tokens: int = 800,
    ) -> str:
        """Return one raw assistant response without transport retries.

        response_schema verilmezse implementasyon kendi varsayılan (operasyonel
        karar) şemasını kullanır; farklı bir yapılandırılmış çıktı isteyen
        çağıranlar (ör. video-geneli özet) kendi şemasını geçirebilir.

        max_tokens varsayılanı tek-hedef karar üretimi için yeterlidir; birden
        çok hedef analizini tek JSON'da birleştiren çağıranlar (video-geneli
        özet gibi) çıktının yarıda kesilip geçersiz JSON üretmesini önlemek
        için daha yüksek bir değer geçirmelidir.
        """

    @abstractmethod
    async def unload(self) -> None:
        """Explicitly release the configured local model."""
