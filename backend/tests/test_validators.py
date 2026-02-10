"""Unit tests for validators."""
import pytest
from src.utils.validators import (
    validate_email,
    validate_password_strength,
    sanitize_string,
)


def test_validate_email():
    assert validate_email("user@example.com") is True
    assert validate_email("user.name+tag@domain.co.uk") is True
    assert validate_email("invalid") is False
    assert validate_email("") is False
    assert validate_email("a" * 256) is False


def test_validate_password_strength():
    ok, _ = validate_password_strength("Short1")
    assert ok is False
    ok, _ = validate_password_strength("nouppercase1")
    assert ok is False
    ok, _ = validate_password_strength("NOLOWERCASE1")
    assert ok is False
    ok, _ = validate_password_strength("NoNumbers")
    assert ok is False
    ok, msg = validate_password_strength("ValidPass1")
    assert ok is True
    assert msg == ""
