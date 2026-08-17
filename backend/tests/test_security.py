from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_refresh_token,
)


def test_access_and_refresh_tokens_have_distinct_types() -> None:
    user_id = uuid4()
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)

    assert decode_access_token(access_token) == user_id
    assert decode_refresh_token(refresh_token.token)["jti"] == refresh_token.jti

    with pytest.raises(HTTPException):
        decode_access_token(refresh_token.token)


def test_refresh_token_hash_is_not_the_raw_token() -> None:
    refresh_token = create_refresh_token(uuid4())

    assert hash_refresh_token(refresh_token.token) != refresh_token.token
    assert hash_refresh_token(refresh_token.token) == hash_refresh_token(
        refresh_token.token
    )
