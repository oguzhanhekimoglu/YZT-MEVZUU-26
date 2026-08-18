"""Controlled Text RAG tool that supplies evidence without making decisions."""

from __future__ import annotations

import asyncio

from operational_decision.contracts.rag import RAGResult, TextRAGRequest
from operational_decision.memory.event_service import EventService
from operational_decision.rag.faiss_store import IndexHealthError
from operational_decision.rag.retriever import (
    NoRelevantContext,
    RetrievalFilterError,
    TextRetriever,
)
from operational_decision.tools.base import BaseTool, ToolExecutionFailure


class TextRAGTool(BaseTool[TextRAGRequest, RAGResult]):
    """Retrieve authoritative local chunks with explicit controlled failures."""

    tool_name = "text_rag"

    def __init__(
        self,
        *,
        retriever: TextRetriever,
        event_id: str,
        request_id: str,
        event_service: EventService | None = None,
    ) -> None:
        """Bind a prevalidated local retriever to the standard tool envelope."""
        super().__init__(
            event_id=event_id,
            request_id=request_id,
            event_service=event_service,
        )
        self.retriever = retriever

    def validate_request(self, request: TextRAGRequest) -> None:
        """Reject empty queries before retrieval."""
        if not request.query.strip():
            raise ValueError("query must not be empty")

    async def execute_internal(self, request: TextRAGRequest) -> RAGResult:
        """Retrieve off the event loop and map controlled RAG outcomes."""
        try:
            sources = await asyncio.to_thread(
                self.retriever.retrieve,
                request.query,
                document_ids=request.document_ids,
                topics=request.topics,
            )
        except NoRelevantContext as error:
            raise ToolExecutionFailure(
                code=error.code,
                message=str(error),
                retryable=False,
            ) from error
        except RetrievalFilterError as error:
            raise ValueError(str(error)) from error
        except IndexHealthError as error:
            raise ToolExecutionFailure(
                code="RAG_INDEX_UNHEALTHY",
                message=str(error),
                retryable=False,
            ) from error
        return RAGResult(
            called=True,
            query_template_id=request.query_template_id,
            sources=sources,
        )