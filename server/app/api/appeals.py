"""
ANCHOR: app.api.appeals
PURPOSE: REST resources for appeals, messages, and officer-reply (stub handlers).
Dependencies: app.api.schemas, application.appeals, application.dialogue, application.learning
CRITICAL: Mutating chat must eventually invoke LangGraph; never invent answers in the router (ANC-GROUND-01, ANC-LG-01).
DO:
- Validate DTOs
- Return 201 on create when implemented
DONT:
- Bypass grounding/escalation for convenience
- Call adapters directly
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.schemas import (
    Appeal,
    CreateAppealRequest,
    CreateMessageRequest,
    Message,
    OfficerReplyRequest,
)

router = APIRouter(tags=["appeals"])


@router.get("/appeals", response_model=list[Appeal])
async def list_appeals() -> list[Appeal]:
    # TODO: application.appeals.list — persistence phase
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"detail": "Appeals list not implemented", "code": "NOT_IMPLEMENTED"},
    )


@router.get("/appeals/{appeal_id}", response_model=Appeal)
async def get_appeal(appeal_id: UUID) -> Appeal:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"detail": f"Get appeal {appeal_id} not implemented", "code": "NOT_IMPLEMENTED"},
    )


@router.post("/appeals", response_model=Appeal, status_code=status.HTTP_201_CREATED)
async def create_appeal(body: CreateAppealRequest) -> Appeal:
    _ = body
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"detail": "Create appeal not implemented", "code": "NOT_IMPLEMENTED"},
    )


@router.post(
    "/appeals/{appeal_id}/messages",
    response_model=Message,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(appeal_id: UUID, body: CreateMessageRequest) -> Message:
    _ = (appeal_id, body)
    # TODO: invoke dialogue LangGraph turn
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"detail": "Post message / agent turn not implemented", "code": "NOT_IMPLEMENTED"},
    )


@router.get("/appeals/{appeal_id}/messages", response_model=list[Message])
async def list_messages(appeal_id: UUID) -> list[Message]:
    _ = appeal_id
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"detail": "List messages not implemented", "code": "NOT_IMPLEMENTED"},
    )


@router.post(
    "/appeals/{appeal_id}/officer-reply",
    response_model=Message,
    status_code=status.HTTP_201_CREATED,
)
async def officer_reply(appeal_id: UUID, body: OfficerReplyRequest) -> Message:
    _ = (appeal_id, body)
    # TODO: learning service + ingest (ANC-LEARN-01)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"detail": "Officer reply / learning not implemented", "code": "NOT_IMPLEMENTED"},
    )
