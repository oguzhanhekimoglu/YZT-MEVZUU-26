"""Text RAG evidence contracts."""

from datetime import date

from pydantic import Field

from operational_decision.contracts.common import StrictContract


class RAGSource(StrictContract):
    """One authoritative retrieved chunk with page provenance."""

    source_id: str = Field(min_length=1, max_length=200)
    chunk_id: str = Field(min_length=1, max_length=200)
    document_id: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=300)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    section_title: str | None = Field(default=None, max_length=500)
    content: str = Field(min_length=1)
    source_priority: int = Field(ge=0)
    authoritative: bool
    revision_date: date | None = None
    effective_date: date | None = None
    similarity: float


class TextRAGRequest(StrictContract):
    """Validated retrieval query and manifest metadata filters."""

    query_template_id: str = Field(min_length=1, max_length=150)
    query: str = Field(min_length=1, max_length=3000)
    document_ids: list[str] = Field(default_factory=list, max_length=6)
    topics: list[str] = Field(default_factory=list, max_length=20)


class RAGResult(StrictContract):
    """Conditional retrieval result supplied as evidence, never as risk."""

    called: bool
    query_template_id: str | None = Field(default=None, max_length=150)
    sources: list[RAGSource] = Field(default_factory=list, max_length=4)
    warnings: list[str] = Field(default_factory=list)
