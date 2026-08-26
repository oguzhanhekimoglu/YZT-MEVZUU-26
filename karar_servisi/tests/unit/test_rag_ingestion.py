"""Unit tests for manifest validation, extraction cleanup, chunking, and embeddings."""
# ruff: noqa: D101, D102, D103

from datetime import date
from pathlib import Path

import numpy as np

from operational_decision.rag.chunker import DocumentChunker
from operational_decision.rag.document_catalog import DocumentCatalog, DocumentDescriptor
from operational_decision.rag.document_loader import (
    DocumentLoader,
    LoadedDocument,
    LoadedPage,
    deterministic_cleanup,
)
from operational_decision.rag.embedding_provider import LocalQwenEmbeddingProvider

ROOT = Path(__file__).resolve().parents[2]


class CharacterTokenizer:
    def encode(self, text: str) -> list[int]:
        return [ord(character) for character in text]

    def decode(self, token_ids: list[int]) -> str:
        return "".join(chr(token_id) for token_id in token_ids)


def descriptor() -> DocumentDescriptor:
    return DocumentDescriptor(
        document_id="DOC",
        filename="doc.pdf",
        authority="AUTH",
        document_type="TEST",
        language="tr",
        topics=["permission"],
        source_priority=100,
        authoritative=True,
        runtime_rag=True,
        role="RUNTIME_RAG",
        revision_date=date(2026, 1, 1),
        effective_date=None,
        sha256="0" * 64,
    )


def test_catalog_validates_roles_checksums_and_sht_metadata() -> None:
    catalog = DocumentCatalog(ROOT / "data/rag/document_manifest.yaml")
    catalog.validate()
    assert len(catalog.runtime_documents) == 6
    assert len(catalog.reference_only_documents) == 1
    sht = catalog.get("SHT_IHA_REV_05")
    assert sht.official_runtime_label == "Rev-05"
    assert sht.internal_change_number == "04"
    assert sht.official_source_verified is True


def test_pdf_loader_preserves_all_pages_and_extracts_text() -> None:
    catalog = DocumentCatalog(ROOT / "data/rag/document_manifest.yaml")
    item = catalog.get("LT_GEN_3_1")
    loaded = DocumentLoader().load(item, catalog.path_for(item))
    assert len(loaded.pages) == 8
    assert loaded.pages[0].page_number == 1
    assert "NOTAM" in " ".join(page.content for page in loaded.pages)


def test_cleanup_removes_only_declared_edge_lines_and_preserves_numbering() -> None:
    text = "HEADER\n\n1.2 Meaningful article\nBody   text\nHEADER"
    assert deterministic_cleanup(text, {"HEADER"}) == "1.2 Meaningful article\nBody text"


def test_chunker_uses_overlap_and_retains_page_metadata() -> None:
    loaded = LoadedDocument(
        descriptor=descriptor(),
        pages=(
            LoadedPage(1, "1. FIRST HEADING\n" + "a" * 15),
            LoadedPage(2, "2. SECOND HEADING\n" + "b" * 15),
        ),
    )
    chunker = DocumentChunker(
        CharacterTokenizer(),
        target_tokens=20,
        max_tokens=24,
        overlap_tokens=5,
    )
    chunks = chunker.chunk(loaded)
    assert len(chunks) >= 2
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2
    assert all(len(CharacterTokenizer().encode(chunk.content)) <= 24 for chunk in chunks)
    assert all(len(chunk.chunk_sha256) == 64 for chunk in chunks)


def test_embedding_provider_forces_float32_and_normalizes(monkeypatch, tmp_path: Path) -> None:
    class FakeModel:
        max_seq_length = 0

        @staticmethod
        def get_embedding_dimension() -> int:
            return 1024

        @staticmethod
        def encode(*args: object, **kwargs: object) -> np.ndarray:
            matrix = np.zeros((2, 1024), dtype=np.float64)
            matrix[0, 0] = 3
            matrix[0, 1] = 4
            matrix[1, 2] = 2
            return matrix

    monkeypatch.setattr(
        "operational_decision.rag.embedding_provider.SentenceTransformer",
        lambda *args, **kwargs: FakeModel(),
    )
    provider = LocalQwenEmbeddingProvider(tmp_path)
    values = provider.encode(["one", "two"])
    assert values.shape == (2, 1024)
    assert values.dtype == np.float32
    assert np.allclose(np.linalg.norm(values, axis=1), 1.0)