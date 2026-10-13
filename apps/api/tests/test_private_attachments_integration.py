import os
from uuid import UUID, uuid4

import pytest
from local_shop.db import build_engine
from local_shop.models import PrivateAttachment, Reservation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_customers_integration import A, B, base, convert, create, headers, inquire
from test_customers_integration import client as client
from test_media_integration import picture

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PostgreSQL required"
)


def upload_private(client, alias="customer-a", tenant=A, key=None, consent="true"):
    return client.post(
        f"/api/v1/stores/{tenant}/private-media?privacy_accepted={consent}",
        headers=headers(client, alias, key) | {"Content-Type": "image/png"},
        content=picture(),
    )


def own_url(media_id, tenant=A):
    return f"/api/v1/me/media/{media_id}/content?store_id={tenant}"


def test_unsubmitted_image_is_only_visible_to_its_uploader(client):
    response = upload_private(client)
    assert response.status_code == 201
    media = response.json()
    assert media["purpose"] == "PRIVATE"
    assert client.get(own_url(media["id"]), headers=headers(client)).status_code == 200
    assert client.get(own_url(media["id"])).status_code == 401
    assert (
        client.get(own_url(media["id"]), headers=headers(client, "customer-b")).status_code == 404
    )
    assert client.get(own_url(media["id"], B), headers=headers(client)).status_code == 404
    path = base() + f"/media/{media['id']}/content"
    assert client.get(path, headers=headers(client, "merchant-a")).status_code == 404
    assert (
        client.patch(
            base() + f"/media/{media['id']}",
            headers=headers(client, "merchant-a"),
            json={"status": "ARCHIVED", "expected_version": 1},
        ).status_code
        == 404
    )
    assert client.get(f"/media/{media['id']}.jpg").status_code == 404


def test_picture_only_inquiry_grants_only_this_shop_access_after_submit(client):
    media = upload_private(client).json()
    response = inquire(client, raw_text="", media_ids=[media["id"]])
    assert response.status_code == 201
    inquiry = response.json()
    assert len(inquiry["attachments"]) == 1
    assert client.get(inquiry["attachments"][0]["url"], headers=headers(client)).status_code == 200
    detail = client.get(
        base() + "/inquiries/" + inquiry["id"], headers=headers(client, "merchant-a")
    )
    assert detail.status_code == 200 and len(detail.json()["attachments"]) == 1
    preview = detail.json()["attachments"][0]["url"]
    assert client.get(preview, headers=headers(client, "merchant-a")).status_code == 200
    assert client.get(preview, headers=headers(client, "merchant-b")).status_code == 404
    assert (
        client.get(preview.replace(A, B), headers=headers(client, "merchant-b")).status_code == 404
    )
    assert (
        client.get(own_url(media["id"]), headers=headers(client, "customer-b")).status_code == 404
    )


def test_picture_only_request_and_unverified_identity_protection(client):
    media = upload_private(client).json()
    response = create(client, raw_text="", media_ids=[media["id"]])
    assert response.status_code == 201 and len(response.json()["attachments"]) == 1
    record = response.json()
    assert (
        client.get(
            "/api/v1/me/records/reservation/" + record["id"], headers=headers(client, "customer-b")
        ).status_code
        == 404
    )
    assert create(client, "customer-b", media_ids=[media["id"]]).status_code == 404
    assert inquire(client, "customer-b", media_ids=[media["id"]]).status_code == 404


def test_cross_tenant_and_public_images_cannot_be_private_attachments(client):
    foreign = upload_private(client, tenant=B).json()
    assert create(client, media_ids=[foreign["id"]]).status_code == 404
    assert inquire(client, media_ids=[foreign["id"]]).status_code == 404
    public = client.post(
        base() + "/media",
        headers=headers(client, "merchant-a") | {"Content-Type": "image/png"},
        content=picture(),
    ).json()
    assert inquire(client, media_ids=[public["id"]]).status_code == 404
    assert (
        client.get(own_url(public["id"]), headers=headers(client, "merchant-a")).status_code == 404
    )


def test_private_file_never_becomes_public_product_or_logo(client):
    media = upload_private(client).json()
    row = inquire(client, media_ids=[media["id"]]).json()
    assert row["id"]
    category = client.post(
        base() + "/categories", headers=headers(client, "merchant-a"), json={"name": "合成类"}
    ).json()
    product = client.post(
        base() + "/products",
        headers=headers(client, "merchant-a"),
        json={"name": "合成品", "category_id": category["id"], "unit": "份", "status": "PUBLISHED"},
    ).json()
    assert (
        client.put(
            base() + f"/products/{product['id']}/images",
            headers=headers(client, "merchant-a"),
            json={"media_ids": [media["id"]], "expected_version": 1},
        ).status_code
        == 404
    )
    assert (
        client.put(
            base() + "/store",
            headers=headers(client, "merchant-a"),
            json={"name": "bad", "expected_version": 1, "logo_media_id": media["id"]},
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/stores/{A}/products/{product['id']}/images/{media['id']}").status_code
        == 404
    )
    assert (
        client.patch(
            base() + f"/media/{media['id']}",
            headers=headers(client, "merchant-a"),
            json={"status": "ACTIVE", "expected_version": 1, "purpose": "PRODUCT"},
        ).status_code
        == 422
    )


def test_conversion_preserves_customer_images_but_hides_merchant_internal_images(client):
    customer_media = upload_private(client).json()
    inquiry = inquire(client, media_ids=[customer_media["id"]]).json()
    private = client.post(
        base() + "/private-media",
        headers=headers(client, "merchant-a") | {"Content-Type": "image/png"},
        content=picture("blue"),
    )
    assert private.status_code == 201
    merchant_media = private.json()
    result = convert(client, inquiry, media_ids=[merchant_media["id"]])
    assert result.status_code == 201
    assert len(result.json()["attachments"]) == 2
    mine = client.get(
        "/api/v1/me/records/reservation/" + result.json()["id"], headers=headers(client)
    )
    assert mine.status_code == 200 and [a["id"] for a in mine.json()["attachments"]] == [
        customer_media["id"]
    ]
    assert client.get(own_url(merchant_media["id"]), headers=headers(client)).status_code == 404
    assert client.get(own_url(customer_media["id"]), headers=headers(client)).status_code == 200


def test_manual_record_attachment_does_not_give_same_named_customer_access(client):
    private = client.post(
        base() + "/private-media",
        headers=headers(client, "merchant-a") | {"Content-Type": "image/png"},
        content=picture(),
    ).json()
    record = client.post(
        base() + "/reservations",
        headers=headers(client, "merchant-a"),
        json={"customer_label": "customer-a", "raw_text": "手工代记", "media_ids": [private["id"]]},
    )
    assert record.status_code == 201 and record.json()["customer_user_id"] is None
    assert client.get(own_url(private["id"]), headers=headers(client)).status_code == 404
    assert (
        client.get(
            record.json()["attachments"][0]["url"], headers=headers(client, "merchant-a")
        ).status_code
        == 200
    )


def test_invalid_attachment_list_rolls_back_record_and_keeps_staged_file(client, pg_settings):
    media = upload_private(client).json()
    assert create(client, media_ids=[media["id"], media["id"]]).status_code == 422
    assert create(client, media_ids=[str(uuid4()) for _ in range(6)]).status_code == 422
    assert create(client, media_ids=[media["id"], str(uuid4())]).status_code == 404
    engine = build_engine(pg_settings)
    try:
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(Reservation)) == 0
            assert session.scalar(select(func.count()).select_from(PrivateAttachment)) == 0
    finally:
        engine.dispose()
    assert len(list(pg_settings.media_root.glob("*.jpg"))) == 1
    assert (
        client.get(
            base() + f"/media/{media['id']}/content", headers=headers(client, "merchant-a")
        ).status_code
        == 404
    )


def test_private_upload_consent_and_idempotency(client, pg_settings):
    assert upload_private(client, consent="false").status_code == 422
    assert not list(pg_settings.media_root.glob("*.jpg"))
    key = str(uuid4())
    first, second = upload_private(client, key=key), upload_private(client, key=key)
    assert first.status_code == 201 and first.json() == second.json()
    assert len(list(pg_settings.media_root.glob("*.jpg"))) == 1


def test_archived_attachment_no_longer_served_and_can_be_restored(client):
    media = upload_private(client).json()
    inquiry = inquire(client, media_ids=[media["id"]]).json()
    assert (
        client.patch(
            base() + f"/media/{media['id']}",
            headers=headers(client, "merchant-a"),
            json={"status": "ARCHIVED", "expected_version": 1},
        ).status_code
        == 200
    )
    assert client.get(own_url(media["id"]), headers=headers(client)).status_code == 404
    assert (
        client.get("/api/v1/me/records/inquiry/" + inquiry["id"], headers=headers(client)).json()[
            "attachments"
        ]
        == []
    )
    assert (
        client.patch(
            base() + f"/media/{media['id']}",
            headers=headers(client, "merchant-a"),
            json={"status": "ACTIVE", "expected_version": 2},
        ).status_code
        == 200
    )
    assert client.get(own_url(media["id"]), headers=headers(client)).status_code == 200


def test_private_attachment_database_rejects_cross_tenant_parent(client, pg_settings):
    media = upload_private(client).json()
    foreign = inquire(client, tenant=B).json()
    engine = build_engine(pg_settings)
    try:
        with pytest.raises(IntegrityError):
            with Session(engine) as session, session.begin():
                session.add(
                    PrivateAttachment(
                        tenant_id=UUID(A),
                        media_id=UUID(media["id"]),
                        inquiry_id=UUID(foreign["id"]),
                        visible_to_customer=True,
                    )
                )
                session.flush()
    finally:
        engine.dispose()


def test_private_data_downgrade_is_not_destructive(client, pg_settings):
    from conftest import migrate

    media = upload_private(client).json()
    with pytest.raises(AssertionError, match="Migration failed"):
        migrate(pg_settings, "downgrade", "0005_customers")
    assert client.get(own_url(media["id"]), headers=headers(client)).status_code == 200


def test_private_image_order_is_preserved_through_conversion(client):
    ids = [upload_private(client).json()["id"] for _ in range(3)]
    ids.sort(reverse=True)
    row = inquire(client, raw_text="", media_ids=ids).json()
    assert [item["id"] for item in row["attachments"]] == ids
    response = convert(client, row)
    assert response.status_code == 201
    mine = client.get(
        "/api/v1/me/records/reservation/" + response.json()["id"], headers=headers(client)
    ).json()
    assert [item["id"] for item in mine["attachments"]] == ids
