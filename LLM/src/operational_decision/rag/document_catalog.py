"""Validated manifest catalog and runtime/reference document allowlists."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from operational_decision.contracts.common import StrictContract


class DocumentCatalogError(ValueError):
    """Report an invalid manifest, checksum, role, or document path."""


class DocumentDescriptor(StrictContract):
    """One validated document manifest record."""

    document_id: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=300)
    authority: str = Field(min_length=1, max_length=100)
    document_type: str = Field(min_length=1, max_length=100)
    language: str = Field(min_length=1, max_length=20)
    topics: list[str] = Field(min_length=1)
    source_priority: int = Field(ge=0)
    authoritative: bool
    runtime_rag: bool
    role: Literal["RUNTIME_RAG", "REFERENCE_ONLY", "NOT_USED"]
    revision_date: date | None = None
    effective_date: date | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    official_runtime_label: str | None = Field(default=None, max_length=100)
    internal_change_number: str | None = Field(default=None, max_length=50)
    internal_change_date: date | None = None
    official_source_verified: bool | None = None

    @model_validator(mode="after")
    def validate_role(self) -> DocumentDescriptor:
        """Keep the explicit role and runtime allowlist flag consistent."""
        expected = "RUNTIME_RAG" if self.runtime_rag else "REFERENCE_ONLY"
        if self.role != expected:
            raise ValueError(f"role {self.role} conflicts with runtime_rag={self.runtime_rag}")
        return self


class DocumentManifest(StrictContract):
    """Top-level document manifest."""

    documents: list[DocumentDescriptor] = Field(min_length=1)


class DocumentCatalog:
    """Load, validate, and resolve the manifest without recursive discovery."""

    def __init__(
        self,
        manifest_path: Path,
        source_documents_dir: Path | None = None,
        reference_only_dir: Path | None = None,
    ) -> None:
        """Load the canonical manifest and establish the two controlled roots."""
        self.manifest_path = manifest_path.resolve()
        rag_root = self.manifest_path.parent
        self.source_documents_dir = (
            source_documents_dir or rag_root / "source_documents"
        ).resolve()
        self.reference_only_dir = (
            reference_only_dir or rag_root / "reference_only"
        ).resolve()
        try:
            raw = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8"))
            self.manifest = DocumentManifest.model_validate(raw)
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise DocumentCatalogError(f"invalid document manifest: {error}") from error
        self._by_id = {item.document_id: item for item in self.manifest.documents}
        if len(self._by_id) != len(self.manifest.documents):
            raise DocumentCatalogError("document_id values must be unique")
        filenames = [item.filename for item in self.manifest.documents]
        if len(set(filenames)) != len(filenames):
            raise DocumentCatalogError("filename values must be unique")

    @property
    def documents(self) -> list[DocumentDescriptor]:
        """Return all manifest records in canonical order."""
        return list(self.manifest.documents)

    @property
    def runtime_documents(self) -> list[DocumentDescriptor]:
        """Return only the explicit runtime allowlist."""
        return [item for item in self.manifest.documents if item.runtime_rag]

    @property
    def reference_only_documents(self) -> list[DocumentDescriptor]:
        """Return documents that must never be indexed."""
        return [item for item in self.manifest.documents if not item.runtime_rag]

    @property
    def manifest_sha256(self) -> str:
        """Hash the exact canonical manifest bytes."""
        return hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()

    def get(self, document_id: str) -> DocumentDescriptor:
        """Resolve a known manifest document ID."""
        try:
            return self._by_id[document_id]
        except KeyError as error:
            raise DocumentCatalogError(f"unknown document_id: {document_id}") from error

    def path_for(self, document: DocumentDescriptor) -> Path:
        """Resolve a document only under the root dictated by its role."""
        root = self.source_documents_dir if document.runtime_rag else self.reference_only_dir
        path = (root / document.filename).resolve()
        if path.parent != root:
            raise DocumentCatalogError(f"unsafe document filename: {document.filename}")
        return path

    def validate(self) -> None:
        """Validate presence, readability, location, checksum, and SHT provenance."""
        for document in self.manifest.documents:
            path = self.path_for(document)
            if not path.is_file():
                raise DocumentCatalogError(
                    f"document missing from expected role directory: {document.filename}"
                )
            try:
                payload = path.read_bytes()
            except OSError as error:
                raise DocumentCatalogError(f"document is not readable: {path}") from error
            checksum = hashlib.sha256(payload).hexdigest()
            if checksum != document.sha256:
                raise DocumentCatalogError(f"checksum mismatch: {document.filename}")
        sht = self._by_id.get("SHT_IHA_REV_05")
        if sht is None:
            raise DocumentCatalogError("SHT_IHA_REV_05 is required")
        if (
            sht.official_runtime_label != "Rev-05"
            or sht.internal_change_number != "04"
            or sht.internal_change_date != date(2020, 7, 12)
            or sht.official_source_verified is not True
            or not sht.runtime_rag
        ):
            raise DocumentCatalogError("SHT-IHA official/internal revision metadata is invalid")