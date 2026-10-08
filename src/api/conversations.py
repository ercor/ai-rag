"""Conversations API endpoints.

POST /v1/conversations — create conversation
GET /v1/conversations — list conversations
GET /v1/conversations/{id} — get conversation with answers
DELETE /v1/conversations/{id} — delete conversation and its answers
"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.container import get_conversation_repository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conversations"])


class CreateConversationRequest(BaseModel):
    """Request body for POST /v1/conversations."""

    title: str | None = None


class ConversationResponse(BaseModel):
    """Response model for a conversation."""

    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationListResponse(BaseModel):
    """Response model for listing conversations."""

    conversations: list[ConversationResponse]
    total: int


class ConversationAnswerResponse(BaseModel):
    """Response model for an answer within a conversation."""

    id: str
    question: str
    answer: str | None
    status: str
    citations: list[dict]
    created_at: str


class ConversationWithAnswersResponse(BaseModel):
    """Response model for a conversation with its answers."""

    id: str
    title: str
    created_at: str
    updated_at: str
    answers: list[ConversationAnswerResponse]


@router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
    response_model=ConversationResponse,
)
async def create_conversation(req: CreateConversationRequest):
    """Create a new conversation.

    Returns the conversation with its UUID and timestamps.
    """
    repo = get_conversation_repository()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ConversationRepository adapter not configured",
        )

    try:
        conversation = await repo.create(title=req.title)
        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at.isoformat(),
            updated_at=conversation.updated_at.isoformat(),
        )
    except Exception as exc:
        logger.error("Failed to create conversation: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create conversation",
        )


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
)
async def list_conversations(limit: int = 20, offset: int = 0):
    """List conversations ordered by most recently updated.

    Query params:
    - limit: max number of conversations (default 20)
    - offset: number to skip (default 0)
    """
    repo = get_conversation_repository()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ConversationRepository adapter not configured",
        )

    try:
        conversations = await repo.list(limit=limit, offset=offset)
        return ConversationListResponse(
            conversations=[
                ConversationResponse(
                    id=c.id,
                    title=c.title,
                    created_at=c.created_at.isoformat(),
                    updated_at=c.updated_at.isoformat(),
                )
                for c in conversations
            ],
            total=len(conversations),
        )
    except Exception as exc:
        logger.error("Failed to list conversations: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list conversations",
        )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationWithAnswersResponse,
)
async def get_conversation(conversation_id: str):
    """Get a conversation with all its answers.

    Returns 404 if the conversation does not exist.
    """
    repo = get_conversation_repository()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ConversationRepository adapter not configured",
        )

    try:
        conversation = await repo.get_by_id(conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation {conversation_id} not found",
            )

        answers = await repo.get_answers(conversation_id)

        return ConversationWithAnswersResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at.isoformat(),
            updated_at=conversation.updated_at.isoformat(),
            answers=[
                ConversationAnswerResponse(
                    id=a.id,
                    question=a.question,
                    answer=a.answer,
                    status=a.status,
                    citations=a.citations,
                    created_at=a.created_at.isoformat(),
                )
                for a in answers
            ],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to get conversation %s: %s", conversation_id, exc, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get conversation",
        )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(conversation_id: str):
    """Delete a conversation and all its linked answers.

    Returns 204 on success (no content).
    """
    repo = get_conversation_repository()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ConversationRepository adapter not configured",
        )

    try:
        await repo.delete(conversation_id)
    except Exception as exc:
        logger.error(
            "Failed to delete conversation %s: %s",
            conversation_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation",
        )
