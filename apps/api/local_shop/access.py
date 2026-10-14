"""Request-scoped database and server-derived merchant authorization."""

from types import SimpleNamespace
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .formal_auth import resolve
from .identity import DEMO_USERS, read_demo_token, require_local
from .models import Tenant, TenantMember, User


class IdempotencyInput(BaseModel):
    key: str = Field(min_length=8, max_length=100)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value):
        if not value.isascii() or not all(c.isalnum() or c in "-_." for c in value):
            raise ValueError("Invalid idempotency key")
        return value


def build_access(settings, engine):
    def database():
        with Session(engine) as session:
            try:
                with session.begin():
                    yield session
            except BaseException:
                for path in session.info.get("new_media_paths", []):
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass  # Orphan is never public without a committed association.
                raise

    def actor(request: Request, session: Session = Depends(database, scope="function")):
        bearer = request.headers.get("Authorization", "")
        if bearer.startswith("Bearer ls1_"):
            return resolve(session, settings, bearer[7:])
        if not settings.dev_auth_enabled:
            raise HTTPException(401, "AUTHENTICATION_REQUIRED")
        require_local(request)
        bearer = request.headers.get("Authorization", "")
        if not bearer.startswith("Bearer "):
            raise HTTPException(401, "INVALID_TOKEN")
        try:
            claims = read_demo_token(bearer[7:], settings)
            if claims["kind"] != "development" or claims["sub"] not in DEMO_USERS.values():
                raise HTTPException(401, "INVALID_TOKEN")
            uid = UUID(claims["sub"])
        except (jwt.InvalidTokenError, ValueError):
            raise HTTPException(401, "INVALID_TOKEN") from None
        user = session.get(User, uid)
        if user is None or user.status != "ACTIVE" or user.identity_type != "DEVELOPMENT":
            raise HTTPException(401, "INVALID_IDENTITY")
        return uid

    def authorize(session, tenant_id, uid):
        row = session.execute(
            select(TenantMember, Tenant)
            .join(Tenant)
            .where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.user_id == uid,
                TenantMember.status == "ACTIVE",
                Tenant.status == "ACTIVE",
                TenantMember.role.in_(["OWNER", "STAFF"]),
            )
            .with_for_update(read=True, of=Tenant)
        ).first()
        if row is None:
            raise HTTPException(404, "TENANT_NOT_FOUND")
        return row[0]

    def key_value(idempotency_key: str = Header(..., alias="Idempotency-Key")):
        try:
            return IdempotencyInput(key=idempotency_key).key
        except ValueError:
            raise HTTPException(422, "INVALID_IDEMPOTENCY_KEY") from None

    def optional_key_value(idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
        return key_value(idempotency_key) if idempotency_key is not None else None

    return SimpleNamespace(
        database=database,
        actor=actor,
        authorize=authorize,
        key_value=key_value,
        optional_key_value=optional_key_value,
    )
