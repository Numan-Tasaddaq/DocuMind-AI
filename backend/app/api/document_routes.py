import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.core.config import get_settings
from app.database.session import get_db
from app.models.auth_models import AppUser, UserDocument
from app.schemas.document import DocumentOut, UploadDocumentsResponse
from app.schemas.auth import MessageResponse
from app.services.document_parser import DocumentParserError, parse_document
from app.services.rag_service import delete_document_vectors, index_user_document

router = APIRouter(prefix="/api/documents", tags=["Documents"])
settings = get_settings()

MAX_UPLOAD_FILES = 5
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx"}


def _get_current_user(db: Session, authorization: str | None) -> AppUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(str(payload.get("sub")))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc

    user = db.execute(select(AppUser).where(AppUser.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


def _safe_extension(filename: str) -> str:
    parts = filename.rsplit(".", 1)
    if len(parts) != 2:
        return ""
    return parts[1].lower()


def _documents_root() -> Path:
    root = Path(__file__).resolve().parents[2] / "storage" / "documents"
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.post("/upload", response_model=UploadDocumentsResponse, status_code=status.HTTP_201_CREATED)
async def upload_documents(
    files: list[UploadFile] = File(...),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UploadDocumentsResponse:
    user = _get_current_user(db, authorization)
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded.")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_UPLOAD_FILES} files can be uploaded at once.",
        )

    uploaded: list[UserDocument] = []
    skipped: list[str] = []
    user_dir = _documents_root() / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    indexed_document_ids: list[uuid.UUID] = []
    created_file_paths: list[Path] = []

    for file in files:
        original_filename = (file.filename or "").strip()
        extension = _safe_extension(original_filename)
        if not original_filename or extension not in ALLOWED_EXTENSIONS:
            skipped.append(f"{original_filename or 'unnamed file'}: unsupported file type")
            continue

        file_bytes = await file.read()
        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            skipped.append(f"{original_filename}: exceeds 10MB limit")
            continue

        try:
            extracted_text = parse_document(file_bytes, extension)
        except DocumentParserError as exc:
            skipped.append(f"{original_filename}: {exc}")
            continue
        except Exception:
            skipped.append(f"{original_filename}: failed to parse")
            continue

        stored_filename = f"{uuid.uuid4()}.{extension}"
        file_path = user_dir / stored_filename
        file_path.write_bytes(file_bytes)
        created_file_paths.append(file_path)

        record = UserDocument(
            user_id=user.id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_extension=extension,
            mime_type=file.content_type,
            file_size_bytes=len(file_bytes),
            extracted_text=extracted_text,
        )
        db.add(record)
        db.flush()

        try:
            index_user_document(
                user_id=user.id,
                document_id=record.id,
                original_filename=original_filename,
                extension=extension,
                file_path=file_path,
                extracted_text=extracted_text,
            )
            indexed_document_ids.append(record.id)
        except Exception as exc:
            # Keep uploaded document saved even if vector indexing fails.
            skipped.append(f"{original_filename}: uploaded, but failed to index for retrieval ({exc})")

        uploaded.append(record)

    if not uploaded and skipped:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="; ".join(skipped))

    try:
        db.commit()
    except Exception:
        db.rollback()
        for indexed_id in indexed_document_ids:
            delete_document_vectors(indexed_id)
        for created_path in created_file_paths:
            if created_path.exists():
                created_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded documents.",
        )
    for row in uploaded:
        db.refresh(row)

    return UploadDocumentsResponse(uploaded=[DocumentOut.model_validate(row) for row in uploaded], skipped=skipped)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    user = _get_current_user(db, authorization)
    documents = db.execute(
        select(UserDocument).where(UserDocument.user_id == user.id).order_by(UserDocument.created_at.desc())
    ).scalars().all()
    return [DocumentOut.model_validate(document) for document in documents]


@router.delete("/{document_id}", response_model=MessageResponse)
def delete_document(
    document_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> MessageResponse:
    user = _get_current_user(db, authorization)
    document = db.execute(
        select(UserDocument).where(UserDocument.id == document_id, UserDocument.user_id == user.id)
    ).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    file_path = _documents_root() / str(user.id) / document.stored_filename
    if file_path.exists():
        file_path.unlink()

    delete_document_vectors(document.id)
    db.delete(document)
    db.commit()
    return MessageResponse(message="Document deleted.")
