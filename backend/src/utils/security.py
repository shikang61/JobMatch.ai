"""
Password hashing and JWT token handling. No plain-text passwords in logs.
Uses bcrypt directly (not passlib) to avoid passlib's 72-byte internal test.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Bcrypt accepts max 72 bytes; truncate to avoid ValueError
BCRYPT_MAX_PASSWORD_BYTES = 72
BCRYPT_ROUNDS = 12


def _to_bcrypt_bytes(s: str) -> bytes:
    """Truncate password to 72 bytes for bcrypt (required by algorithm)."""
    raw = (s or "").encode("utf-8")
    if len(raw) <= BCRYPT_MAX_PASSWORD_BYTES:
        return raw
    return raw[:BCRYPT_MAX_PASSWORD_BYTES]


def hash_password(plain_password: str) -> str:
    """Hash password with bcrypt (cost factor 12). Empty password allowed for demo."""
    secret = _to_bcrypt_bytes(plain_password or "")
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(secret, salt).decode("ascii")


def verify_password(plain_password: str, hashed: str) -> bool:
    """Verify plain password against hash."""
    secret = _to_bcrypt_bytes(plain_password or "")
    try:
        return bcrypt.checkpw(secret, hashed.encode("ascii"))
    except Exception:
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    """Create JWT access token. Subject is typically user id (str)."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode = {"sub": str(subject), "exp": expire, "type": "access"}
    return jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token() -> str:
    """Create long-lived refresh token (opaque random string, store hash in DB)."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Store only hash of refresh token."""
    return hashlib.sha256(token.encode()).hexdigest()


def decode_access_token(token: str) -> str | None:
    """Decode and validate access token. Returns sub (user id) or None."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "access":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def get_refresh_token_expiry() -> datetime:
    """Expiry time for refresh tokens."""
    settings = get_settings()
    return datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
