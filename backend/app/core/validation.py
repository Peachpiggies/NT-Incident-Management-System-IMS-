"""Shared input policies for identity and user-provided values."""

import re

EMAIL_PATTERN = re.compile(
    r"^(?=.{3,254}$)[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
    re.IGNORECASE,
)
PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_email(value: str) -> str:
    """Validate and normalize an email address without accepting display names."""
    normalized = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid email address")
    return normalized


def validate_phone(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    normalized = value.strip().replace(" ", "").replace("-", "")
    if not PHONE_PATTERN.fullmatch(normalized):
        raise ValueError("Phone number must use E.164 format, e.g. +66812345678")
    return normalized


def validate_password(value: str) -> str:
    if len(value) < 12 or len(value) > 128:
        raise ValueError("Password must be 12-128 characters")
    requirements = [
        any(character.islower() for character in value),
        any(character.isupper() for character in value),
        any(character.isdigit() for character in value),
        any(not character.isalnum() for character in value),
    ]
    if not all(requirements):
        raise ValueError(
            "Password must include uppercase, lowercase, number, and special character"
        )
    return value
