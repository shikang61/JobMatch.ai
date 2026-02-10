"""
Authentication: register, login, refresh, delete account. Rate limited.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import CurrentUserId
from src.api.middleware.rate_limit import check_auth_rate_limit
from src.database.connection import get_db
from src.models.user import User, RefreshToken
from src.models.profile import UserProfile
from src.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    get_refresh_token_expiry,
)
from src.utils.validators import validate_email, validate_password_strength
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(default="", max_length=256)  # Optional for demo


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(default="", max_length=256)  # Optional for demo


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


def _expires_in_seconds() -> int:
    from src.config import get_settings
    return get_settings().access_token_expire_minutes * 60


@router.post("/register", response_model=TokenResponse)
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user. Rate limited (5/15min per IP). Password optional for demo."""
    check_auth_rate_limit(request)

    if body.password and body.password.strip():
        ok, msg = validate_password_strength(body.password)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
    if not validate_email(body.email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    result = await db.execute(select(User).where(User.email == body.email.lower()))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password or ""),
    )
    db.add(user)
    await db.flush()

    refresh = create_refresh_token()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh),
        expires_at=get_refresh_token_expiry(),
    )
    db.add(rt)
    await db.commit()
    await db.refresh(user)

    logger.info("User registered", extra={"user_id": str(user.id)})
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=refresh,
        expires_in=_expires_in_seconds(),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Login. Returns access and refresh tokens. Rate limited. Password optional for demo."""
    check_auth_rate_limit(request)

    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    # Demo mode: skip password check when password is empty
    if body.password and body.password.strip():
        if not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")

    refresh = create_refresh_token()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh),
        expires_at=get_refresh_token_expiry(),
    )
    db.add(rt)
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=refresh,
        expires_in=_expires_in_seconds(),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Issue new access token using refresh token. Rate limited."""
    check_auth_rate_limit(request)

    token_hash = hash_refresh_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken, User).join(User, RefreshToken.user_id == User.id).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    refresh_token_row, user = row
    # Optional: revoke old refresh token (rotate)
    await db.delete(refresh_token_row)
    new_refresh = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(new_refresh),
            expires_at=get_refresh_token_expiry(),
        )
    )
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=new_refresh,
        expires_in=_expires_in_seconds(),
    )


@router.delete("/account")
async def delete_account(
    user_id: CurrentUserId,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Permanently delete the current user's account and all associated data.
    Profile (and job matches, prep kits, sessions) and refresh tokens are removed first, then user.
    """
    check_auth_rate_limit(request)
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        # Delete profile first so FK chain: profile -> job_matches -> prep_kits -> sessions
        profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == UUID(user_id))
        )
        profile = profile_result.scalar_one_or_none()
        if profile:
            await db.delete(profile)
        await db.delete(user)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception("Account deletion failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to delete account. Please try again or contact support.",
        ) from e
    logger.info("User account deleted", extra={"user_id": user_id})
    return {"detail": "Account and all data have been deleted."}
