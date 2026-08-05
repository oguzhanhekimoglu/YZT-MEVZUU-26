"""Qwen-tokenized deterministic page-aware document chunking."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol, cast

from transformers import AutoTokenizer

from operational_decision.rag.document_loader import LoadedDocument, deterministic_cleanup


class TokenCounter(Protocol):
    """Minimal canonical tokenizer interface used by the chunker."""

    def encode(self, text: str) -> list[int]:
        """Encode text without special tokens."""

    def decode(self, token_ids: list[int]) -> str:
        """Decode token IDs to source text."""


class QwenTokenCounter:
    """Offline Qwen3-Embedding tokenizer used as the canonical token counter."""

    def __init__(self, local_model_path: Path) -> None:
        """Load only local tokenizer assets and never contact a model hub."""
        if not local_model_path.is_dir():
            raise FileNotFoundError(f"local embedding model missing: {local_model_path}")
        self._tokenizer: Any = AutoTokenizer.from_pretrained(
            local_model_path,
            local_files_only=True,
            trust_remote_code=False,
        )

    def encode(self, text: str) -> list[int]:
        """Encode text without model-added special tokens."""
        return cast(list[int], self._tokenizer.encode(text, add_special_tokens=False))

    def decode(self, token_ids: list[int]) -> str:
        """Decode while retaining meaningful source structure."""
        return cast(
            str,
            self._tokenizer.decode(
                token_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            ),
        )


@dataclass(frozen=True)
class TextChunk:
    """One page-aware chunk and all required index metadata."""

    chunk_id: str
    chunk_index: int
    document_id: str
    filename: str
    language: str
    page_start: int
    page_end: int
    section_title: str | None
    content: str
    topics: list[str]
    source_priority: int
    authoritative: bool
    revision_date: date | None
    effective_date: date | None
    document_sha256: str
    chunk_sha256: str

    def as_dict(self) -> dict[str, object]:
        """Serialize dates as ISO strings for deterministic JSONL."""
        value = asdict(self)
        for key in ("revision_date", "effective_date"):
            item = value[key]
            value[key] = item.isoformat() if isinstance(item, date) else None
        return value


@dataclass(frozen=True)
class _TokenReference:
    token_id: int
    page_number: int
    section_title: str | None


_HEADING = re.compile(r"^(?:\d+(?:\.\d+){0,5}\.?\s+|[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ\s/()\-]{5,})")


def _section_title(content: str) -> str | None:
    for line in content.splitlines():
        candidate = line.strip()
        if 3 <= len(candidate) <= 180 and _HEADING.match(candidate):
            return candidate
    return None


class DocumentChunker:
    """Create deterministic 600-token windows with 100-token overlap."""

    def __init__(
        self,
        tokenizer: TokenCounter,
        *,
        target_tokens: int = 600,
        max_tokens: int = 750,
        overlap_tokens: int = 100,
    ) -> None:
        """Set the binding chunk sizes and validate their invariants."""
        if not 0 <= overlap_tokens < target_tokens <= max_tokens:
            raise ValueError("chunk token settings are inconsistent")
        self.tokenizer = tokenizer
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, document: LoadedDocument) -> list[TextChunk]:
        """Chunk one loaded document while retaining page and section metadata."""
        refs: list[_TokenReference] = []
        current_section: str | None = None
        for page in document.pages:
            current_section = _section_title(page.content) or current_section
            for token_id in self.tokenizer.encode(page.content + "\n"):
                refs.append(_TokenReference(token_id, page.page_number, current_section))
        if not refs:
            return []

        step = self.target_tokens - self.overlap_tokens
        chunks: list[TextChunk] = []
        start = 0
        ordinal = 1
        while start < len(refs):
            if start > 0 and len(refs) - start <= self.overlap_tokens:
                break
            selected = refs[start : start + self.target_tokens]
            token_ids = [item.token_id for item in selected]
            content = deterministic_cleanup(self.tokenizer.decode(token_ids))
            if not content:
                start += step
                continue
            encoded_content = self.tokenizer.encode(content)
            if len(encoded_content) > self.max_tokens:
                content = deterministic_cleanup(
                    self.tokenizer.decode(encoded_content[: self.max_tokens])
                )
            page_start = selected[0].page_number
            page_end = selected[-1].page_number
            chunk_id = f"{document.descriptor.document_id}_P{page_start}_C{ordinal:03d}"
            chunks.append(
                TextChunk(
                    chunk_id=chunk_id,
                    chunk_index=ordinal - 1,
                    document_id=document.descriptor.document_id,
                    filename=document.descriptor.filename,
                    language=document.descriptor.language,
                    page_start=page_start,
                    page_end=page_end,
                    section_title=selected[0].section_title,
                    content=content,
                    topics=list(document.descriptor.topics),
                    source_priority=document.descriptor.source_priority,
                    authoritative=document.descriptor.authoritative,
                    revision_date=document.descriptor.revision_date,
                    effective_date=document.descriptor.effective_date,
                    document_sha256=document.descriptor.sha256,
                    chunk_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                )
            )
            ordinal += 1
            start += step
        return chunks