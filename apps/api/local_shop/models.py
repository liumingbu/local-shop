import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    account_code: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True)
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    identity_type: Mapped[str] = mapped_column(String(20))
    display_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="ck_users_status"),)


class Tenant(Base):
    __tablename__ = "tenants"
    version: Mapped[int] = mapped_column(Integer, default=1)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'SUSPENDED')", name="ck_tenants_status"),
        CheckConstraint("version >= 1", name="ck_tenant_version"),
    )


class TenantMember(Base):
    __tablename__ = "tenant_members"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    __table_args__ = (
        CheckConstraint("role IN ('OWNER', 'STAFF')", name="ck_members_role"),
        CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="ck_members_status"),
    )


class Store(Base):
    __tablename__ = "stores"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    published: Mapped[bool] = mapped_column(default=False)
    public_contact: Mapped[str] = mapped_column(String(200), default="")
    public_address: Mapped[str] = mapped_column(String(300), default="")
    business_hours: Mapped[str] = mapped_column(String(200), default="")
    delivery_note: Mapped[str] = mapped_column(String(500), default="")
    allow_pickup: Mapped[bool] = mapped_column(default=False)
    allow_delivery: Mapped[bool] = mapped_column(default=False)
    logo_media_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "logo_media_id"],
            ["media_objects.tenant_id", "media_objects.id"],
            name="fk_store_logo_same_tenant",
        ),
    )


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_category_tenant_id"),
        CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="ck_category_status"),
        CheckConstraint("version >= 1", name="ck_category_version"),
    )


class Product(Base):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(20))
    spec: Mapped[str] = mapped_column(String(120), default="")
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    supply_status: Mapped[str] = mapped_column(String(20), default="CONFIRM")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_product_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_product_same_tenant_category",
        ),
        CheckConstraint("status IN ('DRAFT','PUBLISHED','ARCHIVED')", name="ck_product_status"),
        CheckConstraint(
            "supply_status IN ('REGULAR','CONFIRM','UNAVAILABLE')", name="ck_product_supply"
        ),
        CheckConstraint("reference_price IS NULL OR reference_price >= 0", name="ck_product_price"),
        CheckConstraint("version >= 1", name="ck_product_version"),
        Index("ix_products_tenant_status", "tenant_id", "status"),
    )


class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    customer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    source_inquiry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    business_number: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    contact_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    contact_phone: Mapped[str] = mapped_column(String(50), default="", server_default="")
    delivery_address: Mapped[str] = mapped_column(String(500), default="", server_default="")
    confirmed_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    privacy_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confirmed_text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(30))
    customer_label: Mapped[str] = mapped_column(String(100))
    raw_text: Mapped[str] = mapped_column(Text)
    items: Mapped[list] = mapped_column(JSONB, default=list)
    fulfillment_method: Mapped[str] = mapped_column(String(20))
    expected_time_note: Mapped[str] = mapped_column(String(200), default="")
    internal_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="PENDING_CONFIRMATION")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_inquiry_id", name="uq_inquiry_single_conversion"),
        ForeignKeyConstraint(
            ["tenant_id", "source_inquiry_id"],
            ["inquiries.tenant_id", "inquiries.id"],
            name="fk_reservation_inquiry_tenant",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_reservation_tenant_id"),
        CheckConstraint("version >= 1", name="ck_reservation_version"),
        CheckConstraint(
            "source IN ('MERCHANT_PHONE','MERCHANT_WECHAT','MERCHANT_IN_STORE',"
            "'CUSTOMER_MINIAPP','INQUIRY_CONVERSION')",
            name="ck_reservation_source",
        ),
        CheckConstraint(
            "fulfillment_method IN ('PICKUP','DELIVERY')", name="ck_reservation_method"
        ),
        CheckConstraint(
            "status IN ('PENDING_CONFIRMATION','CONFIRMED','PREPARING','READY',"
            "'OUT_FOR_DELIVERY','COMPLETED','CANCELLED')",
            name="ck_reservation_status",
        ),
        Index("ix_reservation_tenant_due", "tenant_id", "confirmed_due_at"),
        Index("ix_reservation_tenant_expected", "tenant_id", "expected_at"),
        Index("ix_reservation_tenant_number", "tenant_id", "business_number"),
        Index("ix_reservation_tenant_status_created", "tenant_id", "status", "created_at"),
    )


class RecordEvent(Base):
    __tablename__ = "record_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reservation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(40), default="STATUS_CHANGED")
    note: Mapped[str] = mapped_column(Text, default="")
    visible_to_customer: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["reservations.tenant_id", "reservations.id"],
            name="fk_event_same_tenant",
        ),
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(160), primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MediaObject(Base):
    __tablename__ = "media_objects"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    purpose: Mapped[str] = mapped_column(String(20))
    privacy_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    mime_type: Mapped[str] = mapped_column(String(30), default="image/jpeg")
    size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_media_tenant_id"),
        CheckConstraint("purpose IN ('PRODUCT','LOGO','PRIVATE')", name="ck_media_purpose"),
        CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="ck_media_status"),
        CheckConstraint("size > 0 AND width > 0 AND height > 0", name="ck_media_dimensions"),
    )


class ProductMedia(Base):
    __tablename__ = "product_media"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    media_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    sort_order: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_image_same_product_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "media_id"],
            ["media_objects.tenant_id", "media_objects.id"],
            name="fk_image_same_media_tenant",
        ),
        UniqueConstraint("tenant_id", "product_id", "sort_order", name="uq_product_image_order"),
    )


class Inquiry(Base):
    __tablename__ = "inquiries"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    customer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    raw_text: Mapped[str] = mapped_column(Text)
    product_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="NEW")
    version: Mapped[int] = mapped_column(Integer, default=1)
    privacy_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_inquiry_tenant_id"),
        CheckConstraint("status IN ('NEW','REPLIED','CLOSED')", name="ck_inquiry_status"),
        Index("ix_inquiry_tenant_customer_created", "tenant_id", "customer_user_id", "created_at"),
    )


class InquiryReply(Base):
    __tablename__ = "inquiry_replies"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    inquiry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    visible_to_customer: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "inquiry_id"],
            ["inquiries.tenant_id", "inquiries.id"],
            name="fk_reply_same_tenant",
        ),
        UniqueConstraint("tenant_id", "inquiry_id", "version", name="uq_reply_version"),
    )


class InquiryEvent(Base):
    __tablename__ = "inquiry_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    inquiry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "inquiry_id"],
            ["inquiries.tenant_id", "inquiries.id"],
            name="fk_inquiry_event_tenant",
        ),
        UniqueConstraint("tenant_id", "inquiry_id", "version", name="uq_inquiry_event_version"),
    )


class PrivateAttachment(Base):
    __tablename__ = "private_attachments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    media_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    inquiry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    visible_to_customer: Mapped[bool] = mapped_column(default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "media_id"],
            ["media_objects.tenant_id", "media_objects.id"],
            name="fk_private_media_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "inquiry_id"],
            ["inquiries.tenant_id", "inquiries.id"],
            name="fk_private_inquiry_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["reservations.tenant_id", "reservations.id"],
            name="fk_private_reservation_tenant",
        ),
        CheckConstraint(
            "num_nonnulls(inquiry_id, reservation_id) = 1", name="ck_private_single_parent"
        ),
        UniqueConstraint("tenant_id", "inquiry_id", "media_id", name="uq_private_inquiry_media"),
        UniqueConstraint(
            "tenant_id", "reservation_id", "media_id", name="uq_private_reservation_media"
        ),
    )


class CancellationRequest(Base):
    __tablename__ = "cancellation_requests"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reservation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="REQUESTED")
    response_note: Mapped[str] = mapped_column(Text, default="")
    decision_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    requested_version: Mapped[int] = mapped_column(Integer)
    decided_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["reservations.tenant_id", "reservations.id"],
            name="fk_cancellation_same_tenant",
        ),
        CheckConstraint(
            "status IN ('REQUESTED','ACCEPTED','REJECTED')", name="ck_cancellation_status"
        ),
        CheckConstraint("requested_version >= 2", name="ck_cancellation_version"),
        CheckConstraint(
            "(status = 'REQUESTED' AND decision_actor_id IS NULL AND decided_at IS NULL "
            "AND decided_version IS NULL) OR (status <> 'REQUESTED' "
            "AND decision_actor_id IS NOT NULL "
            "AND decided_at IS NOT NULL AND decided_version IS NOT NULL "
            "AND decided_version > requested_version)",
            name="ck_cancellation_decision",
        ),
        Index(
            "uq_cancellation_pending",
            "tenant_id",
            "reservation_id",
            unique=True,
            postgresql_where=text("status = 'REQUESTED'"),
        ),
    )


class ConfirmationRevision(Base):
    __tablename__ = "confirmation_revisions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reservation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    proposed_version: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["reservations.tenant_id", "reservations.id"],
            name="fk_confirmation_same_tenant",
        ),
        UniqueConstraint(
            "tenant_id", "reservation_id", "proposed_version", name="uq_confirmation_version"
        ),
        CheckConstraint("proposed_version >= 2", name="ck_confirmation_version"),
        CheckConstraint(
            "(confirmed_version IS NULL AND confirmed_by IS NULL AND confirmed_at IS NULL) "
            "OR (confirmed_version IS NOT NULL AND confirmed_by IS NOT NULL "
            "AND confirmed_at IS NOT NULL AND confirmed_version > proposed_version)",
            name="ck_confirmation_ack",
        ),
    )


class PlatformAdmin(Base):
    __tablename__ = "platform_admins"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_platform_admin_status"),
    )


class ShopInvitation(Base):
    __tablename__ = "shop_invitations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    proposed_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="INVITED")
    version: Mapped[int] = mapped_column(Integer, default=1)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint(
            "status IN ('INVITED','ACCEPTED','DECLINED','APPROVED','REJECTED')",
            name="ck_invitation_status",
        ),
        CheckConstraint("version >= 1", name="ck_invitation_version"),
        CheckConstraint(
            "(status = 'APPROVED' AND tenant_id IS NOT NULL) OR "
            "(status <> 'APPROVED' AND tenant_id IS NULL)",
            name="ck_invitation_tenant",
        ),
        Index("ix_invitation_owner_status", "owner_user_id", "status", "created_at"),
    )


class PlatformOperation(Base):
    __tablename__ = "platform_operations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    key: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"))
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shop_invitations.id"))
    before_status: Mapped[str | None] = mapped_column(String(20))
    after_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("actor_id", "key", name="uq_platform_operation_actor_key"),
        Index("ix_platform_operation_time", "created_at", "id"),
    )


class WeChatIdentity(Base):
    __tablename__ = "wechat_identities"
    appid: Mapped[str] = mapped_column(String(32), primary_key=True)
    openid: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsedLoginCode(Base):
    __tablename__ = "used_login_codes"
    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthRateWindow(Base):
    __tablename__ = "auth_rate_windows"
    bucket: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


class BrowserApproval(Base):
    __tablename__ = "browser_approvals"
    secret_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    consumed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
