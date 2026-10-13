from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, Request

from .config import Settings

DEMO_USERS = {
    "merchant-a": "00000000-0000-4000-8000-000000000001",
    "merchant-b": "00000000-0000-4000-8000-000000000002",
    "customer-a": "00000000-0000-4000-8000-000000000003",
    "customer-b": "00000000-0000-4000-8000-000000000004",
}


def require_local(request: Request):
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "LOCAL_DEVELOPMENT_ONLY")


def issue_demo_token(alias: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": DEMO_USERS[alias],
            "kind": "development",
            "iss": "local-shop-dev",
            "aud": "local-shop",
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        settings.app_secret_key.get_secret_value(),
        algorithm="HS256",
    )


def read_demo_token(token: str, settings: Settings) -> dict:
    return jwt.decode(
        token,
        settings.app_secret_key.get_secret_value(),
        algorithms=["HS256"],
        audience="local-shop",
        issuer="local-shop-dev",
        options={"require": ["sub", "kind", "iat", "exp", "iss", "aud"]},
    )
