import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.database.session import get_db
from app.models.auth_models import AppUser, ChatConversation, ChatMessage
from app.schemas.chat import (
    ChatConversationDetail,
    ChatConversationSummary,
    CreateConversationRequest,
    RenameConversationRequest,
    SendChatMessageRequest,
    SendChatMessageResponse,
)
from app.schemas.auth import MessageResponse
from app.services.gemini_service import generate_gemini_reply

router = APIRouter(prefix="/api/chats", tags=["Chats"])


def _get_current_user(
    db: Session,
    authorization: str | None,
) -> AppUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")

    try:
        user_id = uuid.UUID(subject)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.") from exc

    user = db.execute(select(AppUser).where(AppUser.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


def _serialize_conversation_summary(
    conversation: ChatConversation, message_count: int, last_message_at: datetime | None
) -> ChatConversationSummary:
    return ChatConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        last_message_at=last_message_at,
        message_count=message_count,
    )


def _serialize_conversation_detail(db: Session, conversation: ChatConversation) -> ChatConversationDetail:
    messages = db.execute(
        select(ChatMessage).where(ChatMessage.conversation_id == conversation.id).order_by(ChatMessage.created_at.asc())
    ).scalars().all()
    last_message_at = messages[-1].created_at if messages else None
    return ChatConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        last_message_at=last_message_at,
        message_count=len(messages),
        messages=messages,
    )


def _get_user_conversation_or_404(db: Session, user_id: uuid.UUID, conversation_id: uuid.UUID) -> ChatConversation:
    conversation = db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id,
        )
    ).scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


@router.get("", response_model=list[ChatConversationSummary])
def list_conversations(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> list[ChatConversationSummary]:
    user = _get_current_user(db, authorization)

    rows = db.execute(
        select(
            ChatConversation,
            func.count(ChatMessage.id).label("message_count"),
            func.max(ChatMessage.created_at).label("last_message_at"),
        )
        .outerjoin(ChatMessage, ChatMessage.conversation_id == ChatConversation.id)
        .where(ChatConversation.user_id == user.id)
        .group_by(ChatConversation.id)
        .order_by(ChatConversation.updated_at.desc())
    ).all()

    return [
        _serialize_conversation_summary(
            conversation=row[0],
            message_count=int(row[1] or 0),
            last_message_at=row[2],
        )
        for row in rows
    ]


@router.post("", response_model=ChatConversationDetail, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: CreateConversationRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ChatConversationDetail:
    user = _get_current_user(db, authorization)
    conversation = ChatConversation(user_id=user.id, title=payload.title.strip())
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _serialize_conversation_detail(db, conversation)


@router.get("/{conversation_id}", response_model=ChatConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ChatConversationDetail:
    user = _get_current_user(db, authorization)
    conversation = _get_user_conversation_or_404(db, user.id, conversation_id)
    return _serialize_conversation_detail(db, conversation)


@router.patch("/{conversation_id}", response_model=ChatConversationDetail)
def rename_conversation(
    conversation_id: uuid.UUID,
    payload: RenameConversationRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ChatConversationDetail:
    user = _get_current_user(db, authorization)
    conversation = _get_user_conversation_or_404(db, user.id, conversation_id)
    conversation.title = payload.title.strip()
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(conversation)
    return _serialize_conversation_detail(db, conversation)


@router.delete("/{conversation_id}", response_model=MessageResponse)
def delete_conversation(
    conversation_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> MessageResponse:
    user = _get_current_user(db, authorization)
    conversation = _get_user_conversation_or_404(db, user.id, conversation_id)
    db.delete(conversation)
    db.commit()
    return MessageResponse(message="Conversation deleted.")


@router.post("/{conversation_id}/messages", response_model=SendChatMessageResponse)
def send_chat_message(
    conversation_id: uuid.UUID,
    payload: SendChatMessageRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> SendChatMessageResponse:
    user = _get_current_user(db, authorization)
    conversation = _get_user_conversation_or_404(db, user.id, conversation_id)

    user_prompt = payload.prompt.strip()
    uploaded_context = (
        f"\n\nUploaded files: {', '.join(payload.uploaded_files)}"
        if payload.uploaded_files
        else ""
    )

    user_message = ChatMessage(conversation_id=conversation.id, role="user", content=user_prompt)
    db.add(user_message)
    db.flush()

    try:
        reply = generate_gemini_reply(f"{user_prompt}{uploaded_context}", temperature=0.3, max_output_tokens=700)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI service error: {exc}",
        ) from exc

    assistant_message = ChatMessage(conversation_id=conversation.id, role="assistant", content=reply)
    db.add(assistant_message)
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_message)
    return SendChatMessageResponse(
        reply=reply,
        conversation_id=conversation.id,
        assistant_message=assistant_message,
    )
