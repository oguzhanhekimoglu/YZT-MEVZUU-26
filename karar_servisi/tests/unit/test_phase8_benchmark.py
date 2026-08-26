"""Final benchmark fixture and deterministic metric tests."""
# ruff: noqa: D101, D102, D103

from pathlib import Path
from types import SimpleNamespace

from operational_decision.rag.retriever import NoRelevantContext
from scripts.benchmark_pipeline import evaluate_benchmark, load_benchmark

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_IDS = {
    "LT_GEN_1_2",
    "SHT_IHA_REV_05",
    "LT_GEN_3_1",
    "LT_ENR_1_10",
    "LT_GEN_3_3",
    "LT_GEN_1_6",
}
REFERENCE_IDS = {
    "UCUS_IZINLERINE_ILISKIN_EL_KITABI",
}


class DeterministicRetriever:
    def retrieve(self, query: str, *, document_ids=None, topics=None):  # type: ignore[no-untyped-def]
        del query
        if topics and any(str(value).startswith("benchmark_no_") for value in topics):
            raise NoRelevantContext("controlled negative")
        return [
            SimpleNamespace(source_id=f"{document_id}_C1", document_id=document_id)
            for document_id in document_ids or []
        ]


def test_final_fixture_balance_and_metric_acceptance() -> None:
    queries = load_benchmark(
        ROOT / "tests/fixtures/rag_queries/final_benchmark_queries.yaml"
    )
    assert len(queries) == 48
    assert {item["language"] for item in queries} == {"tr", "en"}
    assert sum(not item["expected_document_ids"] for item in queries) == 6
    report = evaluate_benchmark(
        DeterministicRetriever(),  # type: ignore[arg-type]
        queries,
        runtime_document_ids=RUNTIME_IDS,
        reference_only_document_ids=REFERENCE_IDS,
    )
    assert report["status"] == "PASSED"
    assert report["determinism_difference_count"] == 0
    assert report["reference_only_leakage"] == 0