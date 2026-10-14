"""Small invited pilot: explicit recipient response, separate admin role and audit.
No platform access to customer records or credentials is implied by this role.
"""

import hashlib
import json
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    PlatformAdmin,
    PlatformOperation,
    ShopInvitation,
    Store,
    Tenant,
    TenantMember,
    User,
)
from .records import StrictModel, lock_scope


class Invite(StrictModel):
    owner_user_id: UUID | None = None
    owner_account_code: str | None = Field(default=None, pattern=r"^U-[A-F0-9]{12}$")
    proposed_name: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def one_recipient(self):
        if (self.owner_user_id is None) == (self.owner_account_code is None):
            raise ValueError("Exactly one account locator required")
        return self


class Respond(StrictModel):
    expected_version: int = Field(ge=1)
    decision: Literal["ACCEPTED", "DECLINED"]


class Review(StrictModel):
    expected_version: int = Field(ge=1)
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=1, max_length=500)


class TenantStatus(StrictModel):
    expected_version: int = Field(ge=1)
    status: Literal["ACTIVE", "SUSPENDED"]
    reason: str = Field(min_length=1, max_length=500)


def admin_only(session, uid):
    role = session.get(PlatformAdmin, uid)
    if role is None or role.status != "ACTIVE":
        raise HTTPException(403, "PLATFORM_ADMIN_REQUIRED")


def invitation_json(row, owner=False):
    value = {
        "id": str(row.id),
        "proposed_name": row.proposed_name,
        "status": row.status,
        "version": row.version,
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "created_at": row.created_at.isoformat(),
    }
    if not owner:
        value["owner_user_id"] = str(row.owner_user_id)
    return value


def tenant_json(row):
    return {
        "id": str(row.id),
        "display_name": row.display_name,
        "status": row.status,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
    }


def operation(session, uid, key, action_name, payload, action):
    body = payload.model_dump(mode="json")
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    lock_scope(session, f"platform:{uid}:{key}")
    previous = session.scalar(
        select(PlatformOperation).where(
            PlatformOperation.actor_id == uid, PlatformOperation.key == key
        )
    )
    if previous:
        if previous.action != action_name or previous.payload_hash != digest:
            raise HTTPException(409, "IDEMPOTENCY_CONFLICT")
        return previous.response
    response, audit = action()
    session.add(
        PlatformOperation(
            actor_id=uid,
            key=key,
            action=action_name,
            payload_hash=digest,
            response=response,
            **audit,
        )
    )
    session.flush()
    return response


def page_result(session, query, page, limit, mapper, ordering):
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(*ordering).offset((page - 1) * limit).limit(limit))
    return {"items": [mapper(row) for row in rows], "total": total, "page": page, "limit": limit}


def build_router(access):
    router = APIRouter(prefix="/api/v1")
    database, actor, key_value = access.database, access.actor, access.key_value

    @router.get("/platform/me")
    def me(uid: UUID = Depends(actor), session: Session = Depends(database, scope="function")):
        admin_only(session, uid)
        return {"user_id": str(uid), "role": "PLATFORM_ADMIN"}

    @router.get("/platform/tenants")
    def tenants(
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        admin_only(session, uid)
        return page_result(
            session, select(Tenant), page, limit, tenant_json, (Tenant.created_at, Tenant.id)
        )

    @router.get("/platform/invitations")
    def invitations(
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        admin_only(session, uid)
        return page_result(
            session,
            select(ShopInvitation),
            page,
            limit,
            invitation_json,
            (ShopInvitation.created_at.desc(), ShopInvitation.id),
        )

    @router.post("/platform/invitations", status_code=201)
    def invite(
        payload: Invite,
        uid: UUID = Depends(actor),
        key: str = Depends(key_value),
        session: Session = Depends(database, scope="function"),
    ):
        admin_only(session, uid)

        def action():
            owner = session.scalar(
                select(User)
                .where(
                    User.account_code == payload.owner_account_code
                    if payload.owner_account_code
                    else User.id == payload.owner_user_id
                )
                .with_for_update(read=True)
            )
            administrator = session.get(User, uid)
            if (
                owner is None
                or owner.status != "ACTIVE"
                or (administrator.identity_type == "WECHAT" and owner.identity_type != "WECHAT")
            ):
                raise HTTPException(404, "INVITATION_OWNER_NOT_FOUND")
            row = ShopInvitation(owner_user_id=owner.id, proposed_name=payload.proposed_name)
            session.add(row)
            session.flush()
            return invitation_json(row), {
                "invitation_id": row.id,
                "before_status": None,
                "after_status": row.status,
                "reason": payload.reason,
            }

        return operation(session, uid, key, "INVITE_SHOP_OWNER", payload, action)

    @router.get("/me/shop-invitations")
    def mine(
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        query = select(ShopInvitation).where(ShopInvitation.owner_user_id == uid)
        return page_result(
            session,
            query,
            page,
            limit,
            lambda row: invitation_json(row, owner=True),
            (ShopInvitation.created_at.desc(), ShopInvitation.id),
        )

    @router.post("/me/shop-invitations/{invitation_id}/response")
    def respond(
        invitation_id: UUID,
        payload: Respond,
        uid: UUID = Depends(actor),
        key: str = Depends(key_value),
        session: Session = Depends(database, scope="function"),
    ):
        def action():
            row = session.scalar(
                select(ShopInvitation)
                .where(ShopInvitation.id == invitation_id, ShopInvitation.owner_user_id == uid)
                .with_for_update()
            )
            if row is None:
                raise HTTPException(404, "INVITATION_NOT_FOUND")
            if row.version != payload.expected_version:
                raise HTTPException(409, "VERSION_CONFLICT")
            if row.status != "INVITED":
                raise HTTPException(409, "INVITATION_RESPONSE_NOT_ALLOWED")
            before = row.status
            row.status, row.version = payload.decision, row.version + 1
            session.flush()
            return invitation_json(row, owner=True), {
                "invitation_id": row.id,
                "before_status": before,
                "after_status": row.status,
                "reason": "Recipient explicitly responded",
            }

        return operation(session, uid, key, f"RESPOND_INVITATION:{invitation_id}", payload, action)

    @router.post("/platform/invitations/{invitation_id}/review")
    def review(
        invitation_id: UUID,
        payload: Review,
        uid: UUID = Depends(actor),
        key: str = Depends(key_value),
        session: Session = Depends(database, scope="function"),
    ):
        admin_only(session, uid)

        def action():
            row = session.scalar(
                select(ShopInvitation).where(ShopInvitation.id == invitation_id).with_for_update()
            )
            if row is None:
                raise HTTPException(404, "INVITATION_NOT_FOUND")
            if row.version != payload.expected_version:
                raise HTTPException(409, "VERSION_CONFLICT")
            allowed = {"ACCEPTED"} if payload.decision == "APPROVED" else {"INVITED", "ACCEPTED"}
            if row.status not in allowed:
                raise HTTPException(409, "INVITATION_REVIEW_NOT_ALLOWED")
            before = row.status
            if payload.decision == "APPROVED":
                owner = session.scalar(
                    select(User).where(User.id == row.owner_user_id).with_for_update(read=True)
                )
                if owner is None or owner.status != "ACTIVE":
                    raise HTTPException(409, "INVITATION_OWNER_INACTIVE")
                tenant = Tenant(id=uuid4(), display_name=row.proposed_name, status="ACTIVE")
                session.add(tenant)
                session.flush()
                session.add(
                    TenantMember(tenant_id=tenant.id, user_id=row.owner_user_id, role="OWNER")
                )
                session.add(Store(tenant_id=tenant.id, name=row.proposed_name, published=False))
                row.tenant_id = tenant.id
            row.status, row.version = payload.decision, row.version + 1
            session.flush()
            return invitation_json(row), {
                "invitation_id": row.id,
                "tenant_id": row.tenant_id,
                "before_status": before,
                "after_status": row.status,
                "reason": payload.reason,
            }

        return operation(session, uid, key, f"REVIEW_INVITATION:{invitation_id}", payload, action)

    @router.post("/platform/tenants/{tenant_id}/status")
    def status(
        tenant_id: UUID,
        payload: TenantStatus,
        uid: UUID = Depends(actor),
        key: str = Depends(key_value),
        session: Session = Depends(database, scope="function"),
    ):
        admin_only(session, uid)

        def action():
            row = session.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
            if row is None:
                raise HTTPException(404, "TENANT_NOT_FOUND")
            if row.version != payload.expected_version:
                raise HTTPException(409, "VERSION_CONFLICT")
            if row.status == payload.status:
                raise HTTPException(409, "TENANT_STATUS_UNCHANGED")
            before = row.status
            row.status, row.version = payload.status, row.version + 1
            session.flush()
            return tenant_json(row), {
                "tenant_id": row.id,
                "before_status": before,
                "after_status": row.status,
                "reason": payload.reason,
            }

        return operation(session, uid, key, f"TENANT_STATUS:{tenant_id}", payload, action)

    @router.get("/platform/audit")
    def audit(
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        uid: UUID = Depends(actor),
        session: Session = Depends(database, scope="function"),
    ):
        admin_only(session, uid)

        def public_fields(row):
            return {
                "id": str(row.id),
                "actor_id": str(row.actor_id),
                "action": row.action,
                "tenant_id": str(row.tenant_id) if row.tenant_id else None,
                "invitation_id": str(row.invitation_id) if row.invitation_id else None,
                "before_status": row.before_status,
                "after_status": row.after_status,
                "reason": row.reason,
                "created_at": row.created_at.isoformat(),
            }

        return page_result(
            session,
            select(PlatformOperation),
            page,
            limit,
            public_fields,
            (PlatformOperation.created_at.desc(), PlatformOperation.id),
        )

    return router
