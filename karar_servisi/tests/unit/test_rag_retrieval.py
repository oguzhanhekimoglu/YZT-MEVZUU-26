"""Unit tests for exact filtered FAISS search and retrieval constraints."""
# ruff: noqa: D103

import json
from pathlib import Path

import numpy as np

from operational_decision.rag.faiss_store import FaissStore
from operational_decision.rag.retriever import NoRelevantContext, RetrievalFilterError


def test_faiss_store_searches_only_prefiltered_rows(tmp_path: Path) -> None:
    matrix = np.zeros((3, 1024), dtype=np.float32)
    matrix[0, 0] = 1
    matrix[1, 1] = 1
    matrix[2, 0] = 0.8
    matrix[2, 1] = 0.6
    store = FaissStore()
    store.add(matrix)
    path = tmp_path / "text.index"
    store.save(path)
    loaded = FaissStore.load(path)
    query = np.zeros(1024, dtype=np.float32)
    query[0] = 1
    results = loaded.search_filtered(query, [1, 2], top_k=2)
    assert [index for index, _ in results] == [2, 1]
    assert all(index != 0 for index, _ in results)


def test_retrieval_errors_are_distinct() -> None:
    assert NoRelevantContext.code == "NO_RELEVANT_CONTEXT"
    assert issubclass(RetrievalFilterError, ValueError)


def test_index_manifest_shape_example_is_json_serializable() -> None:
    value = {
        "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
        "dimension": 1024,
        "normalized": True,
    }
    assert json.loads(json.dumps(value))["dimension"] == 1024