import uuid

from fastapi import APIRouter, Header, HTTPException, status

from app.auth.security import decode_access_token
from app.core.config import get_settings
from app.schemas.ai import GeminiChatRequest, GeminiChatResponse
from app.services.gemini_service import generate_gemini_reply

router = APIRouter(prefix="/api/ai", tags=["AI"])
settings = get_settings()


def _validate_bearer_token(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if not subject:
            raise ValueError("missing sub")
        uuid.UUID(subject)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc


@router.post("/gemini/chat", response_model=GeminiChatResponse)
def gemini_chat(
    payload: GeminiChatRequest,
    authorization: str | None = Header(default=None),
) -> GeminiChatResponse:
    _validate_bearer_token(authorization)
    reply = generate_gemini_reply(
        payload.prompt.strip(),
        temperature=payload.temperature,
        max_output_tokens=payload.max_output_tokens,
    )
    return GeminiChatResponse(model=settings.gemini_model, reply=reply)
