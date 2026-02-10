"""Unit tests for security utilities."""
import pytest
from src.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    create_refresh_token,
    hash_refresh_token,
)


def test_password_hashing():
    pwd = "SecureP@ss1"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert len(hashed) > 20
    assert verify_password(pwd, hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_token_generation():
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    token = create_access_token(user_id)
    assert isinstance(token, str)
    assert len(token) > 20
    decoded = decode_access_token(token)
    assert decoded == user_id
    assert decode_access_token("invalid") is None


def test_refresh_token_and_hash():
    token = create_refresh_token()
    assert isinstance(token, str)
    assert len(token) > 20
    h = hash_refresh_token(token)
    assert h != token
    assert hash_refresh_token(token) == h
