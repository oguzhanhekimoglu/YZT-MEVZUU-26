"""Contract tests for Text RAG request and evidence bounds."""
# ruff: noqa: D103

import pytest
from pydantic import ValidationError

from operational_decision.contracts.rag import RAGResult, TextRAGRequest


def test_text_rag_request_is_strict() -> None:
    request = TextRAGRequest(
        query_template_id="ACTIVE_NOTAM",
        query="NOTAM bağlamı nedir?",
        document_ids=["LT_GEN_3_1"],
    )
    assert request.document_ids == ["LT_GEN_3_1"]
    with pytest.raises(ValidationError):
        TextRAGRequest.model_validate(
            {
                "query_template_id": "ACTIVE_NOTAM",
                "query": "x",
                "unexpected": True,
            }
        )


def test_rag_result_never_contains_risk_or_decision_fields() -> None:
    schema = RAGResult.model_json_schema()
    assert "risk_level" not in schema["properties"]
    assert "decision_code" not in schema["properties"]