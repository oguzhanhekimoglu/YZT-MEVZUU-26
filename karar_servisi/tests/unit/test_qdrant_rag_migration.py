"""Unit tests for the EVREN Qdrant/bge-m3-embed RAG migration pieces."""

import json

import httpx
import numpy as np
import pytest
from qdrant_client import QdrantClient

from operational_decision.rag.embedding_provider import RemoteEmbedProvider
from operational_decision.rag.faiss_store import IndexHealthError
from operational_decision.rag.qdrant_store import QdrantStore


def _in_memory_store(dimension: int = 4) -> QdrantStore:
    client = QdrantClient(location=":memory:")
    store = QdrantStore(client, "test-collection", dimension=dimension)
    store.create()
    return store


def _unit_rows(count: int, dimension: int = 4) -> np.ndarray:
    """One-hot-ish normalized rows so cosine similarity is easy to reason about."""
    matrix = np.zeros((count, dimension), dtype=np.float32)
    for row in range(count):
        matrix[row, row % dimension] = 1.0
    return matrix


def test_qdrant_store_add_and_count() -> None:
    store = _in_memory_store()
    store.add(_unit_rows(3))
    assert store.count == 3


def test_qdrant_store_search_filtered_restricts_to_candidates() -> None:
    store = _in_memory_store()
    store.add(_unit_rows(5))  # point ids 0..4, each aligned to a different axis

    query = np.zeros(4, dtype=np.float32)
    query[2] = 1.0  # en yakın: id=2 (ve id=6%4=2 yok, sadece id=2)

    # candidate set id=2'yi dışarıda tutuyor -> onu değil, kalan en iyi eşleşmeyi almalı
    results_without_2 = store.search_filtered(query, [0, 1, 3, 4], top_k=8)
    returned_ids = [point_id for point_id, _ in results_without_2]
    assert 2 not in returned_ids
    assert set(returned_ids).issubset({0, 1, 3, 4})

    # id=2 adaylardaysa en üstte olmalı (tam eşleşme, skor ~1.0)
    results_with_2 = store.search_filtered(query, [0, 1, 2, 3, 4], top_k=8)
    assert results_with_2[0][0] == 2
    assert results_with_2[0][1] == pytest.approx(1.0, abs=1e-4)


def test_qdrant_store_search_filtered_empty_candidates_returns_empty() -> None:
    store = _in_memory_store()
    store.add(_unit_rows(3))
    assert store.search_filtered(np.zeros(4, dtype=np.float32), [], top_k=4) == []


def test_qdrant_store_search_filtered_rejects_duplicate_candidates() -> None:
    store = _in_memory_store()
    store.add(_unit_rows(3))
    with pytest.raises(ValueError):
        store.search_filtered(np.zeros(4, dtype=np.float32), [0, 0], top_k=4)


def test_qdrant_store_connect_rejects_missing_collection() -> None:
    client = QdrantClient(location=":memory:")
    with pytest.raises(IndexHealthError):
        QdrantStore.connect(client, "does-not-exist", dimension=4)


def test_qdrant_store_connect_rejects_dimension_mismatch() -> None:
    client = QdrantClient(location=":memory:")
    QdrantStore(client, "wrong-dim", dimension=4).create()
    with pytest.raises(IndexHealthError):
        QdrantStore.connect(client, "wrong-dim", dimension=8)


def _fake_embeddings_transport(dimension: int = 1024):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        rows = [
            {"index": i, "embedding": [1.0] + [0.0] * (dimension - 1)}
            for i, _ in enumerate(payload["input"])
        ]
        return httpx.Response(200, json={"data": rows})

    return httpx.MockTransport(handler)


def test_remote_embed_provider_normalizes_and_orders_by_index() -> None:
    provider = RemoteEmbedProvider(
        base_url="https://evren-llmapi.ssyz.org.tr",
        api_key="test-key",
        client=httpx.Client(
            base_url="https://evren-llmapi.ssyz.org.tr",
            transport=_fake_embeddings_transport(dimension=4),
        ),
    )
    provider.dimension = 4
    matrix = provider.encode(["a", "b"])
    assert matrix.shape == (2, 4)
    norms = np.linalg.norm(matrix, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4)


def test_remote_embed_provider_empty_input_returns_empty_matrix() -> None:
    provider = RemoteEmbedProvider(base_url="https://evren-llmapi.ssyz.org.tr", api_key="test-key")
    provider.dimension = 4
    matrix = provider.encode([])
    assert matrix.shape == (0, 4)
