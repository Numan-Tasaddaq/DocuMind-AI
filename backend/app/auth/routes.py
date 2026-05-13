from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import create_access_token, hash_password, verify_password
from app.core.config import get_settings
from app.database.session import get_db
from app.models.auth_models import AppUser, UserLoginHistory
from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
settings = get_settings()


def _get_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _record_login_attempt(
    db: Session,
    request: Request,
    *,
    user_id,
    success: bool,
    failure_reason: str | None = None,
) -> None:
    db.add(
        UserLoginHistory(
            user_id=user_id,
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            success=success,
            failure_reason=failure_reason,
        )
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    existing_user = db.execute(
        select(AppUser).where(AppUser.email == payload.email.strip().lower())
    ).scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")

    cleaned_name = payload.full_name.strip()
    if len(cleaned_name) < 2:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Full name is too short.")

    new_user = AppUser(
        full_name=cleaned_name,
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
    )
    db.add(new_user)
    db.flush()
    _record_login_attempt(db, request, user_id=new_user.id, success=True)
    db.commit()
    db.refresh(new_user)

    token = create_access_token(new_user.id, new_user.email)
    return AuthResponse(access_token=token, user=UserOut.model_validate(new_user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.execute(select(AppUser).where(AppUser.email == payload.email.strip().lower())).scalar_one_or_none()

    if not user:
        _record_login_attempt(
            db,
            request,
            user_id=None,
            success=False,
            failure_reason="email_not_found",
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    now = datetime.now(timezone.utc)

    if not user.is_active:
        _record_login_attempt(
            db,
            request,
            user_id=user.id,
            success=False,
            failure_reason="account_inactive",
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled.")

    if user.locked_until and user.locked_until > now:
        _record_login_attempt(
            db,
            request,
            user_id=user.id,
            success=False,
            failure_reason="account_locked",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to repeated failed logins.",
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_login_attempts:
            user.locked_until = now + timedelta(minutes=settings.account_lock_minutes)
            user.failed_login_attempts = 0

        _record_login_attempt(
            db,
            request,
            user_id=user.id,
            success=False,
            failure_reason="invalid_password",
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now

    _record_login_attempt(db, request, user_id=user.id, success=True)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.email)
    return AuthResponse(access_token=token, user=UserOut.model_validate(user))
