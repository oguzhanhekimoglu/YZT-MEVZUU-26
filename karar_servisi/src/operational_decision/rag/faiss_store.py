"""Single global FAISS IndexFlatIP with metadata-first exact subset search."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatMatrix = NDArray[np.float32]


class IndexHealthError(RuntimeError):
    """Report an absent, corrupt, or structurally inconsistent vector index."""


def _faiss() -> Any:
    return importlib.import_module("faiss")


def _normalized_matrix(values: FloatMatrix, dimension: int) -> FloatMatrix:
    matrix = np.asarray(values, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[1] != dimension:
        raise ValueError(f"expected (*, {dimension}) float32 embeddings")
    if matrix.shape[0] and not np.allclose(
        np.linalg.norm(matrix, axis=1), 1.0, atol=1e-4
    ):
        raise ValueError("IndexFlatIP accepts only normalized embeddings")
    return np.ascontiguousarray(matrix, dtype=np.float32)


class FaissStore:
    """Own one global exact inner-product index and reconstruct filtered rows."""

    index_type = "IndexFlatIP"

    def __init__(self, dimension: int = 1024, index: Any | None = None) -> None:
        """Create or wrap a global IndexFlatIP of the binding dimension."""
        self.dimension = dimension
        self.index: Any = index if index is not None else _faiss().IndexFlatIP(dimension)
        if int(self.index.d) != dimension:
            raise IndexHealthError("FAISS dimension mismatch")

    @property
    def count(self) -> int:
        """Return the global indexed vector count."""
        return int(self.index.ntotal)

    def add(self, embeddings: FloatMatrix) -> None:
        """Add normalized float32 rows in metadata order."""
        matrix = _normalized_matrix(embeddings, self.dimension)
        self.index.add(matrix)

    def save(self, path: Path) -> None:
        """Persist the single global index."""
        path.parent.mkdir(parents=True, exist_ok=True)
        _faiss().write_index(self.index, str(path))

    @classmethod
    def load(cls, path: Path, dimension: int = 1024) -> FaissStore:
        """Load a persisted IndexFlatIP and reject other index structures."""
        if not path.is_file():
            raise IndexHealthError(f"FAISS index missing: {path}")
        try:
            index = _faiss().read_index(str(path))
        except Exception as error:
            raise IndexHealthError(f"FAISS index cannot be read: {path}") from error
        if index.__class__.__name__ != "IndexFlatIP":
            raise IndexHealthError("only global IndexFlatIP is allowed")
        return cls(dimension=dimension, index=index)

    def search_filtered(
        self,
        query: NDArray[np.float32],
        candidate_indices: list[int],
        *,
        top_k: int,
    ) -> list[tuple[int, float]]:
        """Run exact inner product only over the prefiltered global row subset."""
        vector = np.asarray(query, dtype=np.float32).reshape(-1)
        if vector.shape != (self.dimension,):
            raise ValueError(f"query embedding must have dimension {self.dimension}")
        norm = float(np.linalg.norm(vector))
        if not np.isclose(norm, 1.0, atol=1e-4):
            raise ValueError("query embedding must be normalized")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if not candidate_indices:
            return []
        if len(set(candidate_indices)) != len(candidate_indices):
            raise ValueError("candidate indices must be unique")
        if min(candidate_indices) < 0 or max(candidate_indices) >= self.count:
            raise IndexHealthError("candidate metadata points outside the global index")
        subset = np.vstack(
            [np.asarray(self.index.reconstruct(int(index)), dtype=np.float32)
             for index in candidate_indices]
        )
        scores = subset @ vector
        order = sorted(
            range(len(candidate_indices)),
            key=lambda offset: (-float(scores[offset]), candidate_indices[offset]),
        )[:top_k]
        return [(candidate_indices[offset], float(scores[offset])) for offset in order]