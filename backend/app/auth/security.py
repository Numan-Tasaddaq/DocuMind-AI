import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: UUID, email: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expires_minutes)
    payload = {"sub": str(user_id), "email": email, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_placeholder_password_hash() -> str:
    # Social auth users do not set local password at creation time.
    random_secret = secrets.token_urlsafe(32)
    return hash_password(random_secret)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
