"""EVREN'in izole takım-Qdrant'ında tek bir koleksiyon — FaissStore ile aynı
arayüz (count, add, search_filtered): önce metadata'da filtrele (bkz.
retriever.py), sonra SADECE o adaylar arasında ara. Fark: FAISS'te bu manuel
reconstruct+dot-product ile yapılıyordu, burada Qdrant'ın kendi
query_filter=HasIdCondition + query_points'i kullanılıyor.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, Filter, HasIdCondition, PointStruct, VectorParams

from operational_decision.rag.faiss_store import IndexHealthError

FloatMatrix = NDArray[np.float32]


class QdrantStore:
    """Own one team-scoped Qdrant collection and search within candidate subsets."""

    index_type = "QdrantCollection"

    def __init__(self, client: QdrantClient, collection_name: str, dimension: int = 1024) -> None:
        """Bind to an already-verified collection."""
        self.client = client
        self.collection_name = collection_name
        self.dimension = dimension

    @property
    def count(self) -> int:
        """Return the collection's point count (exact, not an estimate)."""
        return int(self.client.count(self.collection_name, exact=True).count)

    def add(self, embeddings: FloatMatrix) -> None:
        """Upsert normalized float32 rows, point id = row index (chunk_metadata.jsonl sırasıyla eşleşir)."""
        matrix = np.asarray(embeddings, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[1] != self.dimension:
            raise ValueError(f"expected (*, {self.dimension}) float32 embeddings")
        points = [
            PointStruct(id=index, vector=row.tolist()) for index, row in enumerate(matrix)
        ]
        if points:
            self.client.upsert(self.collection_name, points=points)

    def create(self) -> None:
        """Create a fresh cosine-similarity collection (build-time only, once)."""
        self.client.create_collection(
            self.collection_name,
            vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
        )

    @classmethod
    def connect(cls, client: QdrantClient, collection_name: str, dimension: int = 1024) -> QdrantStore:
        """Verify a collection exists and matches the expected dimension before use."""
        try:
            info = client.get_collection(collection_name)
        except Exception as error:
            raise IndexHealthError(f"Qdrant collection unreachable: {collection_name}") from error
        vectors_config: Any = info.config.params.vectors
        size = getattr(vectors_config, "size", None)
        if size != dimension:
            raise IndexHealthError("Qdrant collection dimension mismatch")
        return cls(client, collection_name, dimension)

    def search_filtered(
        self,
        query: NDArray[np.float32],
        candidate_indices: list[int],
        *,
        top_k: int,
    ) -> list[tuple[int, float]]:
        """Run Qdrant search restricted (query_filter) to the prefiltered candidate subset.

        NOT: FAISS sürümü eşit skorları (-score, index) ile deterministik sıralıyordu;
        Qdrant kendi sıralamasını döner — kayan noktalı skorlarda tam eşitlik pratikte
        çok nadir, bu kabul edilen küçük bir davranış farkı.
        """
        vector = np.asarray(query, dtype=np.float32).reshape(-1)
        if vector.shape != (self.dimension,):
            raise ValueError(f"query embedding must have dimension {self.dimension}")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if not candidate_indices:
            return []
        if len(set(candidate_indices)) != len(candidate_indices):
            raise ValueError("candidate indices must be unique")
        response = self.client.query_points(
            self.collection_name,
            query=vector.tolist(),
            query_filter=Filter(must=[HasIdCondition(has_id=candidate_indices)]),
            limit=top_k,
            with_payload=False,
            with_vectors=False,
        )
        return [(int(point.id), float(point.score)) for point in response.points]
