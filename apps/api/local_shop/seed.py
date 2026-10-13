"""Explicit opt-in synthetic seed; no real customers or production use."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .db import build_engine
from .identity import DEMO_USERS
from .models import Tenant, TenantMember, User


def seed(settings: Settings):
    if settings.app_env not in {"development", "test"} or not settings.dev_auth_enabled:
        raise RuntimeError("Synthetic seed requires explicit development identity mode")
    engine = build_engine(settings)
    try:
        with Session(engine) as session, session.begin():
            for index, (alias, value) in enumerate(DEMO_USERS.items(), start=1):
                uid = UUID(value)
                tid = UUID(f"10000000-0000-4000-8000-{index:012d}")
                user = session.get(User, uid)
                if user is None:
                    session.add(User(id=uid, identity_type="DEVELOPMENT", display_name=alias))
                elif user.identity_type != "DEVELOPMENT":
                    raise RuntimeError("Existing identity collision; no data overwritten")
                if not alias.startswith("merchant-"):
                    continue
                tenant = session.get(Tenant, tid)
                if tenant is None:
                    session.add(Tenant(id=tid, display_name=f"合成演示店{index}"))
                elif tenant.display_name != f"合成演示店{index}":
                    raise RuntimeError("Existing tenant collision; no data overwritten")
                session.flush()
                member = session.scalar(
                    select(TenantMember).where(
                        TenantMember.tenant_id == tid, TenantMember.user_id == uid
                    )
                )
                if member is None:
                    session.add(TenantMember(tenant_id=tid, user_id=uid, role="OWNER"))
    finally:
        engine.dispose()


if __name__ == "__main__":
    seed(Settings())
