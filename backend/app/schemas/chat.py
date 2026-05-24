from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class ChatConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None
    message_count: int = 0


class ChatConversationDetail(ChatConversationSummary):
    messages: list[ChatMessageOut] = Field(default_factory=list)


class CreateConversationRequest(BaseModel):
    title: str = Field(default="New Chat", min_length=1, max_length=160)


class RenameConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)


class SendChatMessageRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    uploaded_files: list[str] = Field(default_factory=list, max_length=5)


class SendChatMessageResponse(BaseModel):
    reply: str
    conversation_id: UUID
    assistant_message: ChatMessageOut
