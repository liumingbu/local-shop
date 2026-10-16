from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from .access import build_access
from .cancellations import build_router as cancellation_router
from .catalog import build_router as catalog_router
from .config import Settings
from .confirmations import build_router as confirmation_router
from .customers import build_router as customer_router
from .daily_workbench import build_router as daily_router
from .db import build_engine, probe_database
from .formal_auth import build_router as formal_router
from .identity import DEMO_USERS, issue_demo_token, read_demo_token, require_local
from .media import build_router as media_router
from .onboarding import build_router as onboarding_router
from .platform import build_router as platform_router
from .records import build_router


class DemoSessionRequest(BaseModel):
    identity: Literal["merchant-a", "merchant-b", "customer-a", "customer-b", "platform-admin"]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = build_engine(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title="local-shop", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    def error(request, status, code, message):
        return JSONResponse(
            status_code=status,
            content={
                "code": code,
                "message": message,
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(request, exc.status_code, str(exc.detail), "请求未被允许")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return error(request, 503, "DATABASE_UNAVAILABLE", "数据库操作暂不可用")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error(request, 422, "INVALID_INPUT", "请求参数不符合要求")

    @app.get("/api/v1/capabilities")
    def capabilities():
        return {
            "wechat_login_configured": settings.wechat_login_enabled,
            "wechat_live_verified": False,
            "wechat_qr": "NOT_CONFIGURED",
            "wechat_messages": "NOT_CONFIGURED",
            "privacy": "DEVELOPMENT_DRAFT",
        }

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready(request: Request):
        try:
            probe_database(engine)
        except SQLAlchemyError:
            return error(request, 503, "DATABASE_UNAVAILABLE", "数据库尚未就绪")
        return {"status": "ready"}

    if settings.dev_auth_enabled:

        @app.post("/api/v1/dev/session")
        def demo_session(payload: DemoSessionRequest, request: Request):
            require_local(request)
            return {
                "access_token": issue_demo_token(payload.identity, settings),
                "token_type": "bearer",
                "expires_in": 900,
                "development_only": True,
            }

        @app.get("/api/v1/dev/me")
        def demo_me(request: Request):
            require_local(request)
            authorization = request.headers.get("Authorization", "")
            if not authorization.startswith("Bearer "):
                raise HTTPException(401, "INVALID_TOKEN")
            try:
                claims = read_demo_token(authorization[7:], settings)
                if claims["kind"] != "development" or claims["sub"] not in DEMO_USERS.values():
                    raise HTTPException(401, "INVALID_TOKEN")
            except jwt.InvalidTokenError:
                raise HTTPException(401, "INVALID_TOKEN") from None
            return {"user_id": claims["sub"], "development_only": True}

    access = build_access(settings, engine)
    app.include_router(onboarding_router(access, settings))
    app.include_router(formal_router(access, settings, engine))
    app.include_router(daily_router(access))
    app.include_router(build_router(access))
    app.include_router(catalog_router(access))
    app.include_router(media_router(access, settings))
    app.include_router(customer_router(access))
    app.include_router(cancellation_router(access))
    app.include_router(confirmation_router(access))
    app.include_router(platform_router(access))
    return app
