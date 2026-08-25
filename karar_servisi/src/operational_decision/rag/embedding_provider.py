"""Offline CPU Qwen3 ve EVREN uzak embedding sağlayıcıları, ikisi de normalized float32 döner."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, cast

import httpx
import numpy as np
from numpy.typing import NDArray
from sentence_transformers import SentenceTransformer

FloatMatrix = NDArray[np.float32]


class EmbeddingProvider(Protocol):
    """Embedding interface shared by build and retrieval."""

    model_id: str
    dimension: int

    def encode(self, texts: list[str]) -> FloatMatrix:
        """Encode texts as normalized float32 rows."""


class LocalQwenEmbeddingProvider:
    """Load Qwen3-Embedding-0.6B from disk on CPU with networking disabled."""

    model_id = "Qwen/Qwen3-Embedding-0.6B"
    dimension = 1024

    def __init__(
        self,
        local_model_path: Path,
        *,
        batch_size: int = 8,
        max_sequence_length: int = 2048,
    ) -> None:
        """Load the verified local model and configure binding runtime limits."""
        if not local_model_path.is_dir():
            raise FileNotFoundError(f"local embedding model missing: {local_model_path}")
        self.local_model_path = local_model_path.resolve()
        self.batch_size = batch_size
        self._model: Any = SentenceTransformer(
            str(self.local_model_path),
            device="cpu",
            trust_remote_code=False,
            local_files_only=True,
        )
        self._model.max_seq_length = max_sequence_length
        model_dimension = cast(int | None, self._model.get_embedding_dimension())
        if model_dimension != self.dimension:
            raise ValueError(
                f"embedding dimension mismatch: expected {self.dimension}, got {model_dimension}"
            )

    def encode(self, texts: list[str]) -> FloatMatrix:
        """Encode locally, force float32, and normalize every nonzero row."""
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        raw = self._model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        matrix = np.asarray(raw, dtype=np.float32)
        if matrix.shape != (len(texts), self.dimension):
            raise ValueError(f"unexpected embedding shape: {matrix.shape}")
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise ValueError("embedding provider returned a zero vector")
        return np.asarray(matrix / norms, dtype=np.float32)


class RemoteEmbedProvider:
    """EVREN'in bge-m3-embed modeliyle (OpenAI-uyumlu /v1/embeddings) çalışan sağlayıcı."""

    model_id = "bge-m3-embed"
    dimension = 1024

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = "bge-m3-embed",
        timeout_seconds: float = 1800.0,  # EVREN dokumantasyonu: acikca belirtilmemis, tutarlilik icin 1800s onerilmis
        client: httpx.Client | None = None,
    ) -> None:
        """Configure the EVREN embeddings endpoint and its team API key."""
        self.model_id = model
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def encode(self, texts: list[str]) -> FloatMatrix:
        """Call EVREN's embeddings endpoint and normalize every nonzero row."""
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        response = self._client.post(
            "/v1/embeddings", json={"model": self.model_id, "input": texts}
        )
        response.raise_for_status()
        body = response.json()
        rows = sorted(body["data"], key=lambda item: item["index"])
        matrix = np.asarray([row["embedding"] for row in rows], dtype=np.float32)
        if matrix.shape != (len(texts), self.dimension):
            raise ValueError(f"unexpected EVREN embedding shape: {matrix.shape}")
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise ValueError("EVREN embedding provider returned a zero vector")
        return np.asarray(matrix / norms, dtype=np.float32)

    def close(self) -> None:
        """Close an internally owned HTTP client."""
        if self._owns_client:
            self._client.close()