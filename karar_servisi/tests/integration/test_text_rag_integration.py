"""Integration tests for build, manifest validation, retrieval, and Text RAG Tool."""
# ruff: noqa: D101, D102, D103

from pathlib import Path

import numpy as np
import pytest
from qdrant_client import QdrantClient

from operational_decision.contracts.common import ToolExecutionStatus
from operational_decision.contracts.rag import TextRAGRequest
from operational_decision.rag.chunker import TextChunk
from operational_decision.rag.document_catalog import DocumentCatalog
from operational_decision.rag.document_loader import LoadedDocument, LoadedPage
from operational_decision.rag.index_builder import (
    TextRAGIndexBuilder,
    load_chunk_metadata,
    validate_index_artifacts,
)
from operational_decision.rag.qdrant_store import QdrantStore
from operational_decision.rag.retriever import (
    NoRelevantContext,
    RetrievalFilterError,
    TextRetriever,
)
from operational_decision.tools.text_rag_tool import TextRAGTool

ROOT = Path(__file__).resolve().parents[2]


class FakeEmbeddingProvider:
    model_id = "Qwen/Qwen3-Embedding-0.6B"
    dimension = 1024

    def encode(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            selected = sum(text.encode("utf-8")) % self.dimension
            matrix[row, selected] = 1
        return matrix


class FakeLoader:
    @staticmethod
    def load(descriptor: object, path: Path) -> LoadedDocument:
        assert path.is_file()
        return LoadedDocument(
            descriptor=descriptor,  # type: ignore[arg-type]
            pages=(LoadedPage(1, "Controlled content"),),
        )


class FakeChunker:
    @staticmethod
    def chunk(document: LoadedDocument) -> list[TextChunk]:
        item = document.descriptor
        content = f"{item.document_id} {' '.join(item.topics)}"
        return [
            TextChunk(
                chunk_id=f"{item.document_id}_P1_C001",
                chunk_index=0,
                document_id=item.document_id,
                filename=item.filename,
                language=item.language,
                page_start=1,
                page_end=1,
                section_title="Controlled section",
                content=content,
                topics=list(item.topics),
                source_priority=item.source_priority,
                authoritative=item.authoritative,
                revision_date=item.revision_date,
                effective_date=item.effective_date,
                document_sha256=item.sha256,
                chunk_sha256="1" * 64,
            )
        ]


def build_retriever(tmp_path: Path) -> tuple[DocumentCatalog, TextRetriever]:
    catalog = DocumentCatalog(ROOT / "data/rag/document_manifest.yaml")
    provider = FakeEmbeddingProvider()
    qdrant_client = QdrantClient(location=":memory:")
    store = QdrantStore(qdrant_client, "test-text-rag", dimension=provider.dimension)
    builder = TextRAGIndexBuilder(
        catalog=catalog,
        loader=FakeLoader(),  # type: ignore[arg-type]
        chunker=FakeChunker(),  # type: ignore[arg-type]
        embedding_provider=provider,
        store=store,
        index_dir=tmp_path,
    )
    summary = builder.build()
    assert summary.indexed_document_count == 6
    assert summary.excluded_document_count == 1
    return catalog, TextRetriever(
        catalog=catalog,
        embedding_provider=provider,
        store=store,
        index_dir=tmp_path,
    )


def test_builder_indexes_only_runtime_allowlist(tmp_path: Path) -> None:
    catalog, retriever = build_retriever(tmp_path)
    metadata = load_chunk_metadata(tmp_path / "chunk_metadata.jsonl")
    assert len(metadata) == 6
    assert {row["document_id"] for row in metadata} == {
        item.document_id for item in catalog.runtime_documents
    }
    assert not {
        item.document_id for item in catalog.reference_only_documents
    }.intersection(row["document_id"] for row in metadata)
    manifest = validate_index_artifacts(
        catalog=catalog,
        index_dir=tmp_path,
        store=retriever.store,
        expected_model_id=FakeEmbeddingProvider.model_id,
    )
    assert manifest["chunk_count"] == 6


def test_retriever_filters_before_exact_search_and_has_no_threshold(tmp_path: Path) -> None:
    _, retriever = build_retriever(tmp_path)
    sources = retriever.retrieve(
        "NOTAM nedir?",
        document_ids=["LT_GEN_3_1"],
    )
    assert [source.document_id for source in sources] == ["LT_GEN_3_1"]
    with pytest.raises(RetrievalFilterError):
        retriever.retrieve(
            "wrong role",
            document_ids=["UCUS_IZINLERINE_ILISKIN_EL_KITABI"],
        )
    with pytest.raises(NoRelevantContext):
        retriever.retrieve("valid empty result", topics=["topic_that_does_not_exist"])


@pytest.mark.asyncio
async def test_text_rag_tool_separates_success_and_no_context(tmp_path: Path) -> None:
    _, retriever = build_retriever(tmp_path)
    tool = TextRAGTool(
        retriever=retriever,
        event_id="evt-rag",
        request_id="req-rag",
    )
    success = await tool.execute(
        TextRAGRequest(
            query_template_id="ACTIVE_NOTAM",
            query="NOTAM nedir?",
            document_ids=["LT_GEN_3_1"],
        ),
        timeout_seconds=5,
    )
    assert success.execution_status is ToolExecutionStatus.SUCCESS
    assert success.data is not None
    assert success.data.called is True
    assert success.source_refs == [success.data.sources[0].source_id]

    no_context = await tool.execute(
        TextRAGRequest(
            query_template_id="NO_MATCH",
            query="Geçerli ama eşleşmeyen filtre",
            topics=["topic_that_does_not_exist"],
        ),
        timeout_seconds=5,
    )
    assert no_context.execution_status is ToolExecutionStatus.ERROR
    assert no_context.error is not None
    assert no_context.error.code == "NO_RELEVANT_CONTEXT"
    assert no_context.error.retryable is False