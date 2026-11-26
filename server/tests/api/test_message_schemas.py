"""
ANCHOR: tests.api.test_message_schemas
PURPOSE: Offline contract — flat POST /messages body vs nested POST /appeals message.
Dependencies: app.api.schemas (Pydantic); no live URLs
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas import CreateAppealRequest, CreateMessageRequest, OfficerReplyRequest


def test_create_message_request_requires_flat_content() -> None:
    body = CreateMessageRequest.model_validate({"content": "Это про договоры на закупку."})
    assert body.content.startswith("Это про")
    assert body.role == "user"


def test_create_message_rejects_nested_message_envelope() -> None:
    """DEMO pitfall: messages body is {"content":...}, not {"message":{"content":...}}."""
    with pytest.raises(ValidationError) as exc:
        CreateMessageRequest.model_validate(
            {"message": {"content": "nested wrongly"}}
        )
    assert "content" in str(exc.value)


def test_create_message_rejects_empty_payload() -> None:
    with pytest.raises(ValidationError):
        CreateMessageRequest.model_validate({})


def test_create_appeal_nests_first_message() -> None:
    body = CreateAppealRequest.model_validate(
        {"message": {"content": "Кто подписывает договоры на закупку?"}}
    )
    assert body.message is not None
    assert "закупку" in body.message.content


def test_create_appeal_allows_missing_message() -> None:
    body = CreateAppealRequest.model_validate({"user_id": "u-1"})
    assert body.message is None
    assert body.user_id == "u-1"


def test_officer_reply_is_flat_content() -> None:
    body = OfficerReplyRequest.model_validate(
        {"content": "Канонический ответ", "source_document_hint": "brandbook"}
    )
    assert body.content.startswith("Канонический")
