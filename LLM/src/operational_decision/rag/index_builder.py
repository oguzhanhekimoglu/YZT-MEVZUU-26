"""Build and validate the canonical local Text RAG index artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from operational_decision.rag.chunker import DocumentChunker, TextChunk
from operational_decision.rag.document_catalog import DocumentCatalog
from operational_decision.rag.document_loader import DocumentLoader, ExtractionError
from operational_decision.rag.embedding_provider import EmbeddingProvider
from operational_decision.rag.faiss_store import FaissStore, IndexHealthError


@dataclass(frozen=True)
class IndexBuildSummary:
    """Counts and identity of a completed index build."""

    indexed_document_count: int
    excluded_document_count: int
    chunk_count: int
    dimension: int
    document_manifest_sha256: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class TextRAGIndexBuilder:
    """Extract, chunk, embed, and persist only manifest runtime documents."""

    def __init__(
        self,
        *,
        catalog: DocumentCatalog,
        loader: DocumentLoader,
        chunker: DocumentChunker,
        embedding_provider: EmbeddingProvider,
        index_dir: Path,
    ) -> None:
        """Bind the validated build dependencies and output directory."""
        self.catalog = catalog
        self.loader = loader
        self.chunker = chunker
        self.embedding_provider = embedding_provider
        self.index_dir = index_dir

    def build(self) -> IndexBuildSummary:
        """Build a single global IndexFlatIP and its auditable metadata."""
        self.catalog.validate()
        chunks: list[TextChunk] = []
        for descriptor in self.catalog.runtime_documents:
            loaded = self.loader.load(descriptor, self.catalog.path_for(descriptor))
            document_chunks = self.chunker.chunk(loaded)
            if not document_chunks:
                raise ExtractionError(
                    f"EXTRACTION_FAILED: no chunks produced for {descriptor.filename}"
                )
            chunks.extend(document_chunks)
        if not chunks:
            raise ExtractionError("EXTRACTION_FAILED: runtime allowlist produced no chunks")
        reference_ids = {
            item.document_id for item in self.catalog.reference_only_documents
        }
        if any(chunk.document_id in reference_ids for chunk in chunks):
            raise RuntimeError("reference-only document entered runtime chunks")

        embeddings = self.embedding_provider.encode([chunk.content for chunk in chunks])
        store = FaissStore(dimension=self.embedding_provider.dimension)
        store.add(embeddings)

        self.index_dir.mkdir(parents=True, exist_ok=True)
        index_path = self.index_dir / "text.index"
        metadata_path = self.index_dir / "chunk_metadata.jsonl"
        manifest_path = self.index_dir / "index_manifest.json"
        store.save(index_path)
        with metadata_path.open("w", encoding="utf-8", newline="\n") as stream:
            for chunk in chunks:
                stream.write(
                    json.dumps(chunk.as_dict(), ensure_ascii=False, sort_keys=True) + "\n"
                )

        index_manifest = {
            "embedding_model": self.embedding_provider.model_id,
            "dimension": self.embedding_provider.dimension,
            "normalized": True,
            "index_type": FaissStore.index_type,
            "document_manifest_sha256": self.catalog.manifest_sha256,
            "chunk_metadata_sha256": _sha256(metadata_path),
            "index_sha256": _sha256(index_path),
            "chunk_count": len(chunks),
            "indexed_document_ids": [
                item.document_id for item in self.catalog.runtime_documents
            ],
            "excluded_document_ids": [
                item.document_id for item in self.catalog.reference_only_documents
            ],
            "built_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        _write_json(manifest_path, index_manifest)
        validate_index_artifacts(
            catalog=self.catalog,
            index_dir=self.index_dir,
            expected_model_id=self.embedding_provider.model_id,
            expected_dimension=self.embedding_provider.dimension,
        )
        return IndexBuildSummary(
            indexed_document_count=len(self.catalog.runtime_documents),
            excluded_document_count=len(self.catalog.reference_only_documents),
            chunk_count=len(chunks),
            dimension=self.embedding_provider.dimension,
            document_manifest_sha256=self.catalog.manifest_sha256,
        )


def load_chunk_metadata(path: Path) -> list[dict[str, Any]]:
    """Load ordered JSONL metadata with explicit format failures."""
    records: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"metadata line {line_number} is not an object")
                records.append(cast(dict[str, Any], value))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise IndexHealthError(f"chunk metadata invalid: {error}") from error
    return records


def validate_index_artifacts(
    *,
    catalog: DocumentCatalog,
    index_dir: Path,
    expected_model_id: str,
    expected_dimension: int = 1024,
) -> dict[str, Any]:
    """Validate index, JSONL, checksums, allowlist, dimension, and model identity."""
    manifest_path = index_dir / "index_manifest.json"
    metadata_path = index_dir / "chunk_metadata.jsonl"
    index_path = index_dir / "text.index"
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("index manifest must be an object")
        manifest = cast(dict[str, Any], raw)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise IndexHealthError(f"index manifest invalid: {error}") from error

    required = {
        "embedding_model",
        "dimension",
        "normalized",
        "index_type",
        "document_manifest_sha256",
        "chunk_metadata_sha256",
        "index_sha256",
        "chunk_count",
        "indexed_document_ids",
        "excluded_document_ids",
        "built_at_utc",
    }
    if not required.issubset(manifest):
        raise IndexHealthError("index manifest fields are incomplete")
    if manifest["embedding_model"] != expected_model_id:
        raise IndexHealthError("embedding model mismatch")
    if manifest["dimension"] != expected_dimension or manifest["normalized"] is not True:
        raise IndexHealthError("embedding shape/normalization mismatch")
    if manifest["index_type"] != FaissStore.index_type:
        raise IndexHealthError("index type mismatch")
    if manifest["document_manifest_sha256"] != catalog.manifest_sha256:
        raise IndexHealthError("document manifest checksum mismatch")
    if manifest["chunk_metadata_sha256"] != _sha256(metadata_path):
        raise IndexHealthError("chunk metadata checksum mismatch")
    if manifest["index_sha256"] != _sha256(index_path):
        raise IndexHealthError("FAISS index checksum mismatch")

    metadata = load_chunk_metadata(metadata_path)
    store = FaissStore.load(index_path, expected_dimension)
    if len(metadata) != store.count or manifest["chunk_count"] != store.count:
        raise IndexHealthError("index and metadata counts differ")
    runtime_ids = [item.document_id for item in catalog.runtime_documents]
    reference_ids = [item.document_id for item in catalog.reference_only_documents]
    if manifest["indexed_document_ids"] != runtime_ids:
        raise IndexHealthError("runtime document allowlist mismatch")
    if manifest["excluded_document_ids"] != reference_ids:
        raise IndexHealthError("reference-only denylist mismatch")
    if any(record.get("document_id") in set(reference_ids) for record in metadata):
        raise IndexHealthError("reference-only document found in index metadata")
    return manifest