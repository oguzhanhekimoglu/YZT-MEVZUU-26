"""Metadata-first exact Text RAG retrieval over the single global index."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from operational_decision.contracts.rag import RAGSource
from operational_decision.rag.document_catalog import DocumentCatalog
from operational_decision.rag.embedding_provider import EmbeddingProvider
from operational_decision.rag.index_builder import (
    load_chunk_metadata,
    validate_index_artifacts,
)
from operational_decision.rag.qdrant_store import QdrantStore

QUERY_INSTRUCTION = (
    "Retrieve authoritative aviation regulation passages relevant to the "
    "Turkish operational verification question. Prefer exact legal and "
    "procedural context in Turkish or English."
)


class RetrievalFilterError(ValueError):
    """Report a malformed or non-runtime metadata filter."""


class NoRelevantContext(RuntimeError):
    """Report zero candidates after a valid filter on a healthy index."""

    code = "NO_RELEVANT_CONTEXT"


class TextRetriever:
    """Validate artifacts and retrieve filtered, deduplicated Top-4 evidence."""

    def __init__(
        self,
        *,
        catalog: DocumentCatalog,
        embedding_provider: EmbeddingProvider,
        store: QdrantStore,
        index_dir: Path,
        candidate_top_k: int = 8,
        final_top_k: int = 4,
        max_chunks_per_document: int = 2,
    ) -> None:
        """Load a healthy index before accepting any retrieval request.

        store, çağıran tarafından zaten bağlanmış (QdrantStore.connect) olmalı —
        vektörler artık uzakta (EVREN'in Qdrant'ı), sadece metadata/manifest yerelde.
        """
        if candidate_top_k != 8 or final_top_k != 4 or max_chunks_per_document != 2:
            raise ValueError("V1 retrieval settings must remain 8/4/2")
        self.catalog = catalog
        self.embedding_provider = embedding_provider
        self.store = store
        self.index_dir = index_dir
        self.candidate_top_k = candidate_top_k
        self.final_top_k = final_top_k
        self.max_chunks_per_document = max_chunks_per_document
        validate_index_artifacts(
            catalog=catalog,
            index_dir=index_dir,
            store=store,
            expected_model_id=embedding_provider.model_id,
            expected_dimension=embedding_provider.dimension,
        )
        self.metadata = load_chunk_metadata(index_dir / "chunk_metadata.jsonl")

    def retrieve(
        self,
        query: str,
        *,
        document_ids: list[str] | None = None,
        topics: list[str] | None = None,
    ) -> list[RAGSource]:
        """Filter first, then exact-search the candidate vector subset without a threshold."""
        clean_query = query.strip()
        if not clean_query:
            raise RetrievalFilterError("query must not be empty")
        runtime_ids = {item.document_id for item in self.catalog.runtime_documents}
        selected_ids = set(document_ids or [])
        if any(not item.strip() for item in selected_ids):
            raise RetrievalFilterError("document filters must not be blank")
        unknown = selected_ids - runtime_ids
        if unknown:
            raise RetrievalFilterError(
                f"document filter is not in runtime allowlist: {sorted(unknown)}"
            )
        selected_topics = {item.strip() for item in topics or []}
        if any(not item for item in selected_topics):
            raise RetrievalFilterError("topic filters must not be blank")

        candidates: list[int] = []
        for index, record in enumerate(self.metadata):
            document_id = str(record.get("document_id", ""))
            record_topics = {str(item) for item in record.get("topics", [])}
            if selected_ids and document_id not in selected_ids:
                continue
            if selected_topics and not selected_topics.intersection(record_topics):
                continue
            candidates.append(index)
        if not candidates:
            raise NoRelevantContext("valid metadata filter produced zero candidate chunks")

        prepared_query = f"{QUERY_INSTRUCTION}\n\nQuery:\n{clean_query}"
        query_embedding = self.embedding_provider.encode([prepared_query])[0]
        ranked = self.store.search_filtered(
            query_embedding,
            candidates,
            top_k=self.candidate_top_k,
        )
        selected: list[tuple[int, float]] = []
        per_document: dict[str, int] = {}
        selected_chunk_indices: dict[str, list[int]] = {}
        for metadata_index, similarity in ranked:
            record = self.metadata[metadata_index]
            document_id = str(record["document_id"])
            chunk_index = int(record["chunk_index"])
            if per_document.get(document_id, 0) >= self.max_chunks_per_document:
                continue
            if any(
                abs(chunk_index - existing) <= 1
                for existing in selected_chunk_indices.get(document_id, [])
            ):
                continue
            selected.append((metadata_index, similarity))
            per_document[document_id] = per_document.get(document_id, 0) + 1
            selected_chunk_indices.setdefault(document_id, []).append(chunk_index)
            if len(selected) == self.final_top_k:
                break
        return [
            self._source(self.metadata[metadata_index], similarity)
            for metadata_index, similarity in selected
        ]

    @staticmethod
    def _source(record: dict[str, Any], similarity: float) -> RAGSource:
        revision = record.get("revision_date")
        effective = record.get("effective_date")
        return RAGSource(
            source_id=str(record["chunk_id"]),
            chunk_id=str(record["chunk_id"]),
            document_id=str(record["document_id"]),
            filename=str(record["filename"]),
            page_start=int(record["page_start"]),
            page_end=int(record["page_end"]),
            section_title=(
                str(record["section_title"]) if record.get("section_title") else None
            ),
            content=str(record["content"]),
            source_priority=int(record["source_priority"]),
            authoritative=bool(record["authoritative"]),
            revision_date=date.fromisoformat(str(revision)) if revision else None,
            effective_date=date.fromisoformat(str(effective)) if effective else None,
            similarity=similarity,
        )