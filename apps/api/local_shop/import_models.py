"""Bounded, tenant-owned CSV preview and per-row durable outcomes."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class CatalogImport(Base):
    __tablename__ = "catalog_imports"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="PREVIEW")
    source_hash: Mapped[str] = mapped_column(String(64))
    rows: Mapped[list] = mapped_column(JSONB)
    new_categories: Mapped[list] = mapped_column(JSONB)
    allow_new_categories: Mapped[bool] = mapped_column(default=False)
    allow_duplicates: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("status IN ('PREVIEW','CONFIRMED')", name="ck_catalog_import_status"),
        CheckConstraint("version >= 1", name="ck_catalog_import_version"),
        Index("ix_catalog_import_tenant_time", "tenant_id", "created_at", "id"),
    )
