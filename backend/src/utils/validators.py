"""
Input validation and sanitization. Used by API and services.
"""
import re
from html import escape

# Email: reasonable format, no leading/trailing spaces
EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)

# Password: min 8 chars, at least one upper, one lower, one digit
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$"
)


def validate_email(email: str) -> bool:
    """Return True if email format is valid."""
    if not email or len(email) > 255:
        return False
    return bool(EMAIL_PATTERN.match(email.strip()))


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Check password meets policy. Returns (ok, message).
    Policy: min 8 chars, at least one uppercase, one lowercase, one digit.
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"
    return True, ""


def sanitize_string(value: str | None, max_length: int = 10_000) -> str:
    """Escape HTML and limit length to prevent XSS and overflow."""
    if value is None:
        return ""
    s = str(value).strip()[:max_length]
    return escape(s)
