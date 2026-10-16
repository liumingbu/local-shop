"""Verified provider identities and revocable opaque sessions; no role self-assignment."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import (
    AuthRateWindow,
    AuthSession,
    BrowserApproval,
    UsedLoginCode,
    User,
    WeChatIdentity,
)
from .proxy_source import auth_source
from .records import StrictModel, lock_scope
from .wechat_login import exchange


def digest(settings, value):
    return hmac.new(
        settings.app_secret_key.get_secret_value().encode(),
        (settings.wechat_appid + "\0" + value).encode(),
        hashlib.sha256,
    ).hexdigest()


def issue(session, settings, uid):
    value = "ls1_" + secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            token_hash=digest(settings, value),
            user_id=uid,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.auth_session_seconds),
        )
    )
    return {
        "access_token": value,
        "token_type": "bearer",
        "expires_in": settings.auth_session_seconds,
        "development_only": False,
    }


def resolve(session, settings, token):
    if not settings.wechat_login_enabled or len(token) > 100:
        raise HTTPException(401, "INVALID_TOKEN")
    row = session.get(AuthSession, digest(settings, token))
    if not row or row.revoked or row.expires_at <= datetime.now(UTC):
        raise HTTPException(401, "SESSION_EXPIRED")
    user = session.get(User, row.user_id)
    if not user or user.status != "ACTIVE" or user.identity_type != "WECHAT":
        raise HTTPException(401, "INVALID_IDENTITY")
    return user.id


def limit(engine, settings, request, kind, maximum=30):
    # Commit rate accounting independently even if the login attempt is rejected.
    host = auth_source(settings, request)
    bucket = (
        kind + ":" + digest(settings, host) + ":" + str(int(datetime.now(UTC).timestamp()) // 60)
    )
    with Session(engine) as session, session.begin():
        query = (
            insert(AuthRateWindow)
            .values(bucket=bucket, count=1)
            .on_conflict_do_update(
                index_elements=[AuthRateWindow.bucket], set_={"count": AuthRateWindow.count + 1}
            )
            .returning(AuthRateWindow.count)
        )
        count = session.scalar(query)
    if count > maximum:
        raise HTTPException(429, "AUTH_RATE_LIMITED")


class Login(StrictModel):
    code: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_-]+$")


class Poll(StrictModel):
    secret: str = Field(min_length=32, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class Approve(StrictModel):
    code: str = Field(min_length=12, max_length=12, pattern=r"^[A-F0-9]{12}$")
    confirmed: bool


def build_router(access, settings, engine):
    router = APIRouter(prefix="/api/v1/auth")
    database, actor = access.database, access.actor

    def configured():
        if not settings.wechat_login_enabled:
            raise HTTPException(503, "WECHAT_LOGIN_NOT_CONFIGURED")

    @router.post("/wechat/session")
    def login(
        payload: Login, request: Request, session: Session = Depends(database, scope="function")
    ):
        configured()
        limit(engine, settings, request, "login")
        code_hash = digest(settings, settings.wechat_appid + ":" + payload.code)
        lock_scope(session, "wechat-code:" + code_hash)
        if session.get(UsedLoginCode, code_hash):
            raise HTTPException(401, "WECHAT_CODE_ALREADY_USED")
        openid = exchange(settings, payload.code)
        lock_scope(session, "wechat-id:" + digest(settings, settings.wechat_appid + ":" + openid))
        mapping = session.get(WeChatIdentity, (settings.wechat_appid, openid))
        if mapping is None:
            user = User(
                id=uuid4(),
                identity_type="WECHAT",
                display_name="微信用户",
                status="ACTIVE",
                account_code="U-" + secrets.token_hex(6).upper(),
            )
            session.add(user)
            session.flush()
            session.add(WeChatIdentity(appid=settings.wechat_appid, openid=openid, user_id=user.id))
        else:
            user = session.get(User, mapping.user_id)
        if user.status != "ACTIVE" or user.identity_type != "WECHAT":
            raise HTTPException(401, "INVALID_IDENTITY")
        session.add(UsedLoginCode(code_hash=code_hash))
        return issue(session, settings, user.id)

    @router.get("/me")
    def me(uid=Depends(actor), session: Session = Depends(database, scope="function")):
        user = session.get(User, uid)
        return {
            "user_id": str(uid),
            "account_code": user.account_code,
            "development_only": user.identity_type == "DEVELOPMENT",
        }

    @router.post("/logout")
    def logout(
        request: Request, uid=Depends(actor), session: Session = Depends(database, scope="function")
    ):
        token = request.headers.get("Authorization", "")[7:]
        row = session.get(AuthSession, digest(settings, token))
        if row and row.user_id == uid:
            row.revoked = True
        return {"logged_out": True}

    @router.post("/browser-approvals", status_code=201)
    def begin(request: Request, session: Session = Depends(database, scope="function")):
        configured()
        limit(engine, settings, request, "browser-start", 10)
        secret = secrets.token_urlsafe(32)
        code = secrets.token_hex(6).upper()
        session.add(
            BrowserApproval(
                secret_hash=digest(settings, secret),
                code_hash=digest(settings, code),
                expires_at=datetime.now(UTC) + timedelta(minutes=3),
            )
        )
        return {
            "secret": secret,
            "code": code,
            "expires_in": 180,
            "instructions": "只在自己的小程序账号中确认自己正在打开的工作台，不替他人确认。",
        }

    @router.post("/browser-approvals/confirm")
    def approve(
        payload: Approve,
        request: Request,
        uid=Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        configured()
        limit(engine, settings, request, "browser-confirm", 10)
        user = session.get(User, uid)
        if user.identity_type != "WECHAT" or not payload.confirmed:
            raise HTTPException(403, "VERIFIED_EXPLICIT_APPROVAL_REQUIRED")
        row = session.scalar(
            select(BrowserApproval)
            .where(BrowserApproval.code_hash == digest(settings, payload.code))
            .with_for_update()
        )
        if (
            not row
            or row.consumed
            or row.user_id is not None
            or row.expires_at <= datetime.now(UTC)
        ):
            raise HTTPException(404, "BROWSER_APPROVAL_UNAVAILABLE")
        row.user_id = uid
        return {"approved": True}

    @router.post("/browser-approvals/poll")
    def poll(
        payload: Poll, request: Request, session: Session = Depends(database, scope="function")
    ):
        configured()
        limit(engine, settings, request, "browser-poll", 90)
        row = session.scalar(
            select(BrowserApproval)
            .where(BrowserApproval.secret_hash == digest(settings, payload.secret))
            .with_for_update()
        )
        if not row or row.consumed or row.expires_at <= datetime.now(UTC):
            raise HTTPException(401, "BROWSER_APPROVAL_EXPIRED")
        if row.user_id is None:
            return {"status": "PENDING"}
        user = session.get(User, row.user_id)
        if not user or user.status != "ACTIVE" or user.identity_type != "WECHAT":
            raise HTTPException(401, "INVALID_IDENTITY")
        row.consumed = True
        return {"status": "APPROVED", **issue(session, settings, user.id)}

    return router
