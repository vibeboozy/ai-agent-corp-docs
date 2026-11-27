"""
ANCHOR: app.api.appeals
PURPOSE: REST resources for appeals, messages, and officer-reply.
Dependencies: app.api.schemas, application.appeals, application.dialogue, application.learning
CRITICAL: Mutating chat invokes LangGraph; never invent answers in the router (ANC-GROUND-01, ANC-LG-01).
DO:
- Validate DTOs
- Return 201 on create
DONT:
- Bypass grounding/escalation for convenience
- Call adapters directly
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import ContainerDep, http_error, require_officer, require_user_headers
from app.api.mapping import to_appeal_dto, to_message_dto
from app.api.schemas import (
    Appeal,
    AppealListResponse,
    CreateAppealRequest,
    CreateAppealResponse,
    CreateMessageRequest,
    CreateMessageResponse,
    MessageListResponse,
    OfficerReplyRequest,
    OfficerReplyResponse,
    LearningInfo,
)
from app.domain.enums import AppealStatus
from app.domain.errors import AppError

router = APIRouter(tags=["appeals"])


@router.get("/appeals", response_model=AppealListResponse)
async def list_appeals(
    container: ContainerDep,
    status_filter: Annotated[AppealStatus | None, Query(alias="status")] = None,
    user_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AppealListResponse:
    try:
        views, total = await container.appeals.list(
            status=status_filter,
            user_id=user_id,
            limit=limit,
            offset=offset,
            created_from=created_from,
            created_to=created_to,
        )
    except AppError as exc:
        raise http_error(exc) from exc
    return AppealListResponse(
        items=[
            to_appeal_dto(
                v.appeal, message_count=v.message_count, question=v.question
            )
            for v in views
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/appeals/{appeal_id}", response_model=Appeal)
async def get_appeal(appeal_id: UUID, container: ContainerDep) -> Appeal:
    try:
        view = await container.appeals.get(appeal_id)
    except AppError as exc:
        raise http_error(exc) from exc
    return to_appeal_dto(
        view.appeal, message_count=view.message_count, question=view.question
    )


@router.post("/appeals", response_model=CreateAppealResponse, status_code=status.HTTP_201_CREATED)
async def create_appeal(
    body: CreateAppealRequest,
    container: ContainerDep,
    _user: Annotated[str | None, Depends(require_user_headers)] = None,
) -> CreateAppealResponse:
    try:
        result = await container.appeals.create(
            user_id=body.user_id or _user,
            user_label=body.user_label,
            topic=body.topic,
            first_message=body.message.content if body.message else None,
        )
    except AppError as exc:
        raise http_error(exc) from exc
    return CreateAppealResponse(
        appeal=to_appeal_dto(
            result.appeal,
            message_count=result.message_count,
            question=result.question,
        ),
        messages=[to_message_dto(m) for m in result.messages],
    )


@router.post(
    "/appeals/{appeal_id}/messages",
    response_model=CreateMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    appeal_id: UUID,
    body: CreateMessageRequest,
    container: ContainerDep,
    _user: Annotated[str | None, Depends(require_user_headers)] = None,
) -> CreateMessageResponse:
    _ = _user
    if body.role == "officer":
        from app.domain.errors import ConflictError

        raise http_error(ConflictError("Use officer-reply endpoint", code="VALIDATION_ERROR"))
    try:
        turn = await container.appeals.post_message(appeal_id=appeal_id, content=body.content)
        count = await container.persistence.count_messages(appeal_id)
    except AppError as exc:
        raise http_error(exc) from exc
    return CreateMessageResponse(
        appeal=to_appeal_dto(turn.appeal, message_count=count),
        messages=[to_message_dto(m) for m in turn.messages],
    )


@router.get("/appeals/{appeal_id}/messages", response_model=MessageListResponse)
async def list_messages(
    appeal_id: UUID,
    container: ContainerDep,
    after_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> MessageListResponse:
    try:
        items = await container.appeals.list_messages(
            appeal_id, after_id=after_id, limit=limit
        )
    except AppError as exc:
        raise http_error(exc) from exc
    return MessageListResponse(
        appeal_id=appeal_id,
        items=[to_message_dto(m) for m in items],
    )


@router.post(
    "/appeals/{appeal_id}/officer-reply",
    response_model=OfficerReplyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def officer_reply(
    appeal_id: UUID,
    body: OfficerReplyRequest,
    container: ContainerDep,
    _: Annotated[None, Depends(require_officer)] = None,
) -> OfficerReplyResponse:
    try:
        result = await container.learning.officer_reply(
            appeal_id=appeal_id,
            content=body.content,
            source_document_hint=body.source_document_hint,
        )
        count = await container.persistence.count_messages(appeal_id)
    except AppError as exc:
        raise http_error(exc) from exc
    return OfficerReplyResponse(
        appeal=to_appeal_dto(result.appeal, message_count=count),
        message=to_message_dto(result.message),
        learning=LearningInfo(
            accepted=result.accepted,
            ingest_job_id=result.ingest_job_id,
            escalation_id=result.escalation_id,
        ),
    )
