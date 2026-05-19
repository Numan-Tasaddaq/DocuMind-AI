import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, Header, HTTPException, Request as FastAPIRequest, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import (
    create_access_token,
    create_placeholder_password_hash,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings
from app.database.session import get_db
from app.models.auth_models import AppUser, UserLoginHistory
from app.schemas.auth import AuthResponse, ChangePasswordRequest, LoginRequest, MessageResponse, SignupRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
settings = get_settings()

ALLOWED_OAUTH_MODES = {"login", "signup"}


def _get_client_ip(request: FastAPIRequest) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _record_login_attempt(
    db: Session,
    request: FastAPIRequest,
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


def _frontend_redirect(*, success: bool, message: str = "", token: str = "", user: AppUser | None = None) -> RedirectResponse:
    payload: dict[str, str] = {"oauth": "success" if success else "error"}
    if message:
        payload["message"] = message
    if token and user:
        payload["token"] = token
        payload["id"] = str(user.id)
        payload["full_name"] = user.full_name
        payload["email"] = user.email

    destination = f"{settings.frontend_auth_callback_url}#{urlencode(payload)}"
    return RedirectResponse(url=destination, status_code=status.HTTP_302_FOUND)


def _fetch_json(url: str, *, method: str = "GET", data: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request_headers = headers.copy() if headers else {}
    encoded_data = None
    if data is not None:
        encoded_data = urlencode(data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    req = Request(url, data=encoded_data, headers=request_headers, method=method)
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_oauth_state(mode: str) -> str:
    nonce = secrets.token_urlsafe(24)
    issued = int(time.time())
    return f"{nonce}.{mode}.{issued}"


def _parse_oauth_state(raw_state: str) -> tuple[str, str, int] | None:
    parts = raw_state.split(".")
    if len(parts) != 3:
        return None
    nonce, mode, issued_raw = parts
    if mode not in ALLOWED_OAUTH_MODES:
        return None
    if not issued_raw.isdigit():
        return None
    return nonce, mode, int(issued_raw)


def _validate_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in {"google", "github"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported provider.")
    return normalized


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
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")

    try:
        user_id = uuid.UUID(subject)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")

    user = db.execute(select(AppUser).where(AppUser.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


def _ensure_provider_credentials(provider: str) -> bool:
    if provider == "google":
        return bool(settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri)
    return bool(settings.github_client_id and settings.github_client_secret and settings.github_redirect_uri)


def _get_oauth_profile(provider: str, code: str) -> dict[str, str] | None:
    if provider == "google":
        token_data = _fetch_json(
            "https://oauth2.googleapis.com/token",
            method="POST",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_redirect_uri,
            },
        )
        access_token = token_data.get("access_token")
        if not access_token:
            return None
        profile = _fetch_json(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        email = (profile.get("email") or "").strip().lower()
        if not email:
            return None
        name = (profile.get("name") or email.split("@")[0]).strip()
        return {"email": email, "full_name": name}

    token_data = _fetch_json(
        "https://github.com/login/oauth/access_token",
        method="POST",
        data={
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "code": code,
            "redirect_uri": settings.github_redirect_uri,
        },
        headers={"Accept": "application/json"},
    )
    access_token = token_data.get("access_token")
    if not access_token:
        return None

    common_headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json", "User-Agent": "DocuMind-AI"}
    profile = _fetch_json("https://api.github.com/user", headers=common_headers)

    email = (profile.get("email") or "").strip().lower()
    if not email:
        emails = _fetch_json("https://api.github.com/user/emails", headers=common_headers)
        if isinstance(emails, list):
            primary = next((entry for entry in emails if entry.get("primary") and entry.get("verified")), None)
            fallback = next((entry for entry in emails if entry.get("verified")), None)
            chosen = primary or fallback
            email = (chosen.get("email") if chosen else "").strip().lower()

    if not email:
        return None

    name = (profile.get("name") or profile.get("login") or email.split("@")[0]).strip()
    return {"email": email, "full_name": name}


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, request: FastAPIRequest, db: Session = Depends(get_db)) -> AuthResponse:
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
def login(payload: LoginRequest, request: FastAPIRequest, db: Session = Depends(get_db)) -> AuthResponse:
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


@router.get("/me", response_model=UserOut)
def get_me(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UserOut:
    user = _get_current_user(db, authorization)
    return UserOut.model_validate(user)


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: FastAPIRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> MessageResponse:
    user = _get_current_user(db, authorization)

    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be different.")

    if not verify_password(payload.current_password, user.password_hash):
        _record_login_attempt(db, request, user_id=user.id, success=False, failure_reason="change_password_invalid_current")
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")

    user.password_hash = hash_password(payload.new_password)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()

    return MessageResponse(message="Password updated successfully.")


@router.get("/oauth/{provider}/start")
def oauth_start(provider: str, mode: str = "login") -> RedirectResponse:
    normalized_provider = _validate_provider(provider)
    flow_mode = mode.strip().lower()
    if flow_mode not in ALLOWED_OAUTH_MODES:
        return _frontend_redirect(success=False, message="Invalid auth mode.")

    if not _ensure_provider_credentials(normalized_provider):
        return _frontend_redirect(success=False, message=f"{normalized_provider.title()} OAuth is not configured.")

    state = _build_oauth_state(flow_mode)
    if normalized_provider == "google":
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    else:
        params = {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_redirect_uri,
            "scope": "read:user user:email",
            "state": state,
        }
        auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    response = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=f"oauth_state_{normalized_provider}",
        value=state,
        max_age=settings.oauth_state_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return response


@router.get("/oauth/{provider}/callback")
def oauth_callback(
    provider: str,
    request: FastAPIRequest,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    normalized_provider = _validate_provider(provider)

    if error:
        return _frontend_redirect(success=False, message=f"{normalized_provider.title()} sign-in cancelled.")

    if not code or not state:
        return _frontend_redirect(success=False, message="OAuth callback is missing required data.")

    cookie_state = request.cookies.get(f"oauth_state_{normalized_provider}")
    if not cookie_state or cookie_state != state:
        return _frontend_redirect(success=False, message="OAuth state validation failed.")

    parsed_state = _parse_oauth_state(state)
    if not parsed_state:
        return _frontend_redirect(success=False, message="OAuth state is invalid.")
    _, mode, issued_at = parsed_state
    if int(time.time()) - issued_at > settings.oauth_state_ttl_seconds:
        return _frontend_redirect(success=False, message="OAuth session expired. Please try again.")

    try:
        profile = _get_oauth_profile(normalized_provider, code)
    except Exception:
        return _frontend_redirect(success=False, message=f"{normalized_provider.title()} authentication failed.")

    if not profile:
        return _frontend_redirect(success=False, message=f"{normalized_provider.title()} did not return profile email.")

    email = profile["email"].strip().lower()
    full_name = profile["full_name"].strip() or email.split("@")[0]
    user = db.execute(select(AppUser).where(AppUser.email == email)).scalar_one_or_none()

    if user and mode == "signup":
        return _frontend_redirect(success=False, message="Account already exists. Please use login.")

    if not user and mode == "login":
        return _frontend_redirect(success=False, message="No account found for this provider. Please sign up first.")

    if not user:
        user = AppUser(
            full_name=full_name,
            email=email,
            password_hash=create_placeholder_password_hash(),
            is_email_verified=True,
            is_active=True,
        )
        db.add(user)
        db.flush()

    if not user.is_active:
        _record_login_attempt(db, request, user_id=user.id, success=False, failure_reason="account_inactive")
        db.commit()
        return _frontend_redirect(success=False, message="Account is disabled.")

    now = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now:
        _record_login_attempt(db, request, user_id=user.id, success=False, failure_reason="account_locked")
        db.commit()
        return _frontend_redirect(success=False, message="Account is temporarily locked.")

    user.last_login_at = now
    user.failed_login_attempts = 0
    user.locked_until = None
    _record_login_attempt(db, request, user_id=user.id, success=True)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.email)
    response = _frontend_redirect(success=True, token=token, user=user)
    response.delete_cookie(f"oauth_state_{normalized_provider}")
    return response
