from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    file_extension: str
    file_size_bytes: int
    created_at: datetime


class UploadDocumentsResponse(BaseModel):
    uploaded: list[DocumentOut]
    skipped: list[str] = []
