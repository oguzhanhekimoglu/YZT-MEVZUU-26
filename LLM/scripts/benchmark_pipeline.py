"""Run the deterministic Phase 8 Text RAG acceptance benchmark."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

import yaml

from operational_decision.rag.document_catalog import DocumentCatalog
from operational_decision.rag.embedding_provider import LocalQwenEmbeddingProvider
from operational_decision.rag.index_builder import validate_index_artifacts
from operational_decision.rag.retriever import NoRelevantContext, TextRetriever

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "tests/fixtures/rag_queries/final_benchmark_queries.yaml"
DEFAULT_REPORT = ROOT / "data/rag/index/final_benchmark_report.json"
MODEL_PATH = ROOT / "data/models/qwen3-embedding-0.6b"
INDEX_DIR = ROOT / "data/rag/index"
THRESHOLDS = {
    "macro_document_recall_at_4": 0.90,
    "per_document_recall_at_4": 0.80,
    "top_1_document_accuracy": 0.70,
    "no_relevant_context_precision": 0.90,
    "reference_only_leakage": 0,
    "manifest_index_mismatch": 0,
    "determinism_difference_count": 0,
}


def load_benchmark(path: Path) -> list[dict[str, Any]]:
    """Load and validate the binding final benchmark fixture."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("queries"), list):
        raise ValueError("benchmark fixture must contain a queries list")
    queries = cast(list[dict[str, Any]], payload["queries"])
    if not 40 <= len(queries) <= 50:
        raise ValueError("final benchmark must contain 40-50 queries")
    identifiers = [str(item.get("query_id", "")) for item in queries]
    if any(not value for value in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("query_id values must be non-empty and unique")
    for item in queries:
        if "expected_document_ids" not in item or not isinstance(
            item["expected_document_ids"], list
        ):
            raise ValueError(f"{item['query_id']} must define expected_document_ids")
        if item.get("language") not in {"tr", "en"}:
            raise ValueError(f"{item['query_id']} has unsupported language")
    return queries


def _retrieve_once(retriever: TextRetriever, item: dict[str, Any]) -> tuple[list[Any], bool]:
    try:
        sources = retriever.retrieve(
            str(item["query"]),
            document_ids=[str(value) for value in item.get("document_ids", [])],
            topics=[str(value) for value in item.get("topics", [])],
        )
    except NoRelevantContext:
        return [], True
    return list(sources[:4]), False


def evaluate_benchmark(
    retriever: TextRetriever,
    queries: list[dict[str, Any]],
    *,
    runtime_document_ids: set[str],
    reference_only_document_ids: set[str],
    manifest_index_mismatch: int = 0,
) -> dict[str, Any]:
    """Calculate retrieval, negative-context, leakage, and determinism metrics."""
    rows: list[dict[str, Any]] = []
    recalls: list[float] = []
    per_document_total: Counter[str] = Counter()
    per_document_hits: Counter[str] = Counter()
    top_one_hits = 0
    relevant_count = 0
    no_context_predictions = 0
    no_context_true_positives = 0
    leakage: set[str] = set()
    determinism_differences = 0

    for item in queries:
        expected = {str(value) for value in item["expected_document_ids"]}
        unknown_expected = expected - runtime_document_ids
        if unknown_expected:
            raise ValueError(f"unknown runtime expected documents: {sorted(unknown_expected)}")
        first, first_no_context = _retrieve_once(retriever, item)
        second, second_no_context = _retrieve_once(retriever, item)
        first_ids = [str(source.source_id) for source in first]
        second_ids = [str(source.source_id) for source in second]
        if first_ids != second_ids or first_no_context != second_no_context:
            determinism_differences += 1
        retrieved_documents = [str(source.document_id) for source in first]
        leakage.update(set(retrieved_documents).intersection(reference_only_document_ids))
        expected_no_context = bool(item.get("expected_no_relevant_context", False))
        if first_no_context:
            no_context_predictions += 1
            if expected_no_context:
                no_context_true_positives += 1
        recall: float | None = None
        if expected:
            relevant_count += 1
            retrieved_set = set(retrieved_documents)
            recall = len(expected.intersection(retrieved_set)) / len(expected)
            recalls.append(recall)
            if retrieved_documents and retrieved_documents[0] in expected:
                top_one_hits += 1
            for document_id in expected:
                per_document_total[document_id] += 1
                if document_id in retrieved_set:
                    per_document_hits[document_id] += 1
        rows.append(
            {
                "query_id": str(item["query_id"]),
                "expected_document_ids": sorted(expected),
                "retrieved_document_ids": retrieved_documents,
                "source_ids": first_ids,
                "recall_at_4": recall,
                "expected_no_relevant_context": expected_no_context,
                "no_relevant_context": first_no_context,
                "deterministic": first_ids == second_ids
                and first_no_context == second_no_context,
            }
        )

    per_document = {
        document_id: per_document_hits[document_id] / total
        for document_id, total in sorted(per_document_total.items())
    }
    macro_recall = sum(recalls) / len(recalls) if recalls else 0.0
    top_one_accuracy = top_one_hits / relevant_count if relevant_count else 0.0
    no_context_precision = (
        no_context_true_positives / no_context_predictions if no_context_predictions else 0.0
    )
    document_query_counts = dict(sorted(per_document_total.items()))
    dataset_valid = (
        len(queries) >= 30
        and {str(item.get("language")) for item in queries} == {"en", "tr"}
        and all(
            document_query_counts.get(document_id, 0) >= 5
            for document_id in runtime_document_ids
        )
    )
    acceptance = {
        "dataset_valid": dataset_valid,
        "macro_document_recall_at_4": macro_recall
        >= THRESHOLDS["macro_document_recall_at_4"],
        "per_document_recall_at_4": bool(per_document)
        and all(
            value >= THRESHOLDS["per_document_recall_at_4"]
            for value in per_document.values()
        ),
        "top_1_document_accuracy": top_one_accuracy
        >= THRESHOLDS["top_1_document_accuracy"],
        "no_relevant_context_precision": no_context_precision
        >= THRESHOLDS["no_relevant_context_precision"],
        "reference_only_leakage": len(leakage) == THRESHOLDS["reference_only_leakage"],
        "manifest_index_mismatch": manifest_index_mismatch
        == THRESHOLDS["manifest_index_mismatch"],
        "determinism": determinism_differences
        == THRESHOLDS["determinism_difference_count"],
    }
    return {
        "benchmark_version": "final-benchmark/1.0",
        "gold_query_count": len(queries),
        "relevant_query_count": relevant_count,
        "negative_query_count": len(queries) - relevant_count,
        "language_counts": dict(Counter(str(item["language"]) for item in queries)),
        "category_counts": dict(Counter(str(item["category"]) for item in queries)),
        "document_query_counts": document_query_counts,
        "macro_document_recall_at_4": macro_recall,
        "per_document_recall_at_4": per_document,
        "top_1_document_accuracy": top_one_accuracy,
        "no_relevant_context_precision": no_context_precision,
        "reference_only_leakage": len(leakage),
        "leaked_document_ids": sorted(leakage),
        "manifest_index_mismatch": manifest_index_mismatch,
        "determinism_difference_count": determinism_differences,
        "thresholds": THRESHOLDS,
        "acceptance": acceptance,
        "status": "PASSED" if all(acceptance.values()) else "FAILED",
        "queries": rows,
    }


def run(dataset_path: Path = DEFAULT_DATASET, report_path: Path = DEFAULT_REPORT) -> dict[str, Any]:
    """Load the healthy local index and persist the final benchmark report."""
    catalog = DocumentCatalog(ROOT / "data/rag/document_manifest.yaml")
    provider = LocalQwenEmbeddingProvider(MODEL_PATH)
    validate_index_artifacts(
        catalog=catalog,
        index_dir=INDEX_DIR,
        expected_model_id=provider.model_id,
        expected_dimension=provider.dimension,
    )
    retriever = TextRetriever(catalog=catalog, embedding_provider=provider, index_dir=INDEX_DIR)
    report = evaluate_benchmark(
        retriever,
        load_benchmark(dataset_path),
        runtime_document_ids={item.document_id for item in catalog.runtime_documents},
        reference_only_document_ids={
            item.document_id for item in catalog.reference_only_documents
        },
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    """Run the benchmark and return a nonzero exit code on any failed threshold."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    arguments = parser.parse_args()
    report = run(arguments.dataset, arguments.report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["status"] != "PASSED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()