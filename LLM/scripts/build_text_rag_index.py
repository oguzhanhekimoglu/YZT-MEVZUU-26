"""Build the local Qwen/FAISS Text RAG index and produce Recall@4."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml

from operational_decision.rag.chunker import DocumentChunker, QwenTokenCounter
from operational_decision.rag.document_catalog import DocumentCatalog
from operational_decision.rag.document_loader import DocumentLoader
from operational_decision.rag.embedding_provider import LocalQwenEmbeddingProvider
from operational_decision.rag.faiss_store import IndexHealthError
from operational_decision.rag.index_builder import (
    IndexBuildSummary,
    TextRAGIndexBuilder,
    validate_index_artifacts,
)
from operational_decision.rag.retriever import TextRetriever

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "data/models/qwen3-embedding-0.6b"
INDEX_DIR = ROOT / "data/rag/index"
GOLD_PATH = ROOT / "tests/fixtures/rag_queries/gold_queries.yaml"


def _load_gold_queries(path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("queries"), list):
        raise ValueError("gold query fixture must contain a queries list")
    return cast(list[dict[str, Any]], raw["queries"])


def evaluate_recall_at_4(
    retriever: TextRetriever,
    gold_queries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate macro document Recall@4 across the controlled gold queries."""
    rows: list[dict[str, Any]] = []
    recalls: list[float] = []
    for item in gold_queries:
        expected = {str(value) for value in item["expected_document_ids"]}
        sources = retriever.retrieve(
            str(item["query"]),
            document_ids=[str(value) for value in item.get("document_ids", [])],
            topics=[str(value) for value in item.get("topics", [])],
        )
        retrieved = {source.document_id for source in sources[:4]}
        recall = len(expected.intersection(retrieved)) / len(expected)
        recalls.append(recall)
        rows.append(
            {
                "query_id": str(item["query_id"]),
                "expected_document_ids": sorted(expected),
                "retrieved_document_ids": sorted(retrieved),
                "recall_at_4": recall,
                "source_ids": [source.source_id for source in sources[:4]],
            }
        )
    macro_recall = sum(recalls) / len(recalls) if recalls else 0.0
    return {
        "gold_query_count": len(rows),
        "recall_at_4": macro_recall,
        "queries": rows,
    }


def main() -> None:
    """Build, validate, benchmark, persist the report, and print a summary."""
    catalog = DocumentCatalog(ROOT / "data/rag/document_manifest.yaml")
    tokenizer = QwenTokenCounter(MODEL_PATH)
    provider = LocalQwenEmbeddingProvider(MODEL_PATH)
    try:
        existing = validate_index_artifacts(
            catalog=catalog,
            index_dir=INDEX_DIR,
            expected_model_id=provider.model_id,
            expected_dimension=provider.dimension,
        )
        summary = IndexBuildSummary(
            indexed_document_count=len(catalog.runtime_documents),
            excluded_document_count=len(catalog.reference_only_documents),
            chunk_count=int(existing["chunk_count"]),
            dimension=int(existing["dimension"]),
            document_manifest_sha256=str(existing["document_manifest_sha256"]),
        )
    except IndexHealthError:
        builder = TextRAGIndexBuilder(
            catalog=catalog,
            loader=DocumentLoader(),
            chunker=DocumentChunker(tokenizer),
            embedding_provider=provider,
            index_dir=INDEX_DIR,
        )
        summary = builder.build()
    retriever = TextRetriever(
        catalog=catalog,
        embedding_provider=provider,
        index_dir=INDEX_DIR,
    )
    report = evaluate_recall_at_4(retriever, _load_gold_queries(GOLD_PATH))
    report.update(
        {
            "indexed_document_count": summary.indexed_document_count,
            "excluded_reference_only_count": summary.excluded_document_count,
            "chunk_count": summary.chunk_count,
            "embedding_dimension": summary.dimension,
            "document_manifest_sha256": summary.document_manifest_sha256,
            "index_manifest_compatible": True,
        }
    )
    report_path = INDEX_DIR / "recall_at_4_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()