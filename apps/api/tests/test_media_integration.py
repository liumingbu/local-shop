import io
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from local_shop.db import build_engine
from local_shop.image_store import MAX_UPLOAD
from local_shop.main import create_app
from local_shop.models import MediaObject, ProductMedia
from PIL import Image
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="Real PostgreSQL required"
)
A = "10000000-0000-4000-8000-000000000001"
B = "10000000-0000-4000-8000-000000000002"


@pytest.fixture
def client(pg_settings):
    with TestClient(create_app(pg_settings), client=("127.0.0.1", 55001)) as app:
        app.tokens = {
            alias: app.post("/api/v1/dev/session", json={"identity": alias}).json()["access_token"]
            for alias in ("merchant-a", "merchant-b")
        }
        yield app


def base(tenant=A):
    return f"/api/v1/merchant/tenants/{tenant}"


def headers(client, alias="merchant-a", key=None):
    return {
        "Authorization": "Bearer " + client.tokens[alias],
        "Idempotency-Key": key or str(uuid4()),
    }


def picture(color="red", size=(24, 24), fmt="PNG", **options):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, fmt, **options)
    return output.getvalue()


def upload(
    client, tenant=A, alias="merchant-a", purpose="PRODUCT", data=None, key=None, mime="image/png"
):
    return client.post(
        base(tenant) + "/media?purpose=" + purpose,
        headers=headers(client, alias, key) | {"Content-Type": mime},
        content=picture() if data is None else data,
    )


def setup_product(client, published=True):
    assert (
        client.put(
            base() + "/store",
            headers=headers(client),
            json={"name": "图片合成店", "published": published, "expected_version": 0},
        ).status_code
        == 200
    )
    cat = client.post(
        base() + "/categories", headers=headers(client), json={"name": "图片分类"}
    ).json()
    response = client.post(
        base() + "/products",
        headers=headers(client),
        json={"category_id": cat["id"], "name": "图片商品", "unit": "份", "status": "PUBLISHED"},
    )
    assert response.status_code == 201
    return response.json()


def attach(client, product, media_ids, version=None):
    return client.put(
        base() + "/products/" + product["id"] + "/images",
        headers=headers(client),
        json={"media_ids": media_ids, "expected_version": version or product["version"]},
    )


def public_url(product, media_id, tenant=A):
    return f"/api/v1/stores/{tenant}/products/{product['id']}/images/{media_id}"


def test_images_require_association_and_order_remove(client):
    product = setup_product(client)
    first = upload(client).json()
    second = upload(client, data=picture("blue")).json()
    assert client.get(public_url(product, first["id"])).status_code == 404
    response = attach(client, product, [second["id"], first["id"]])
    assert response.status_code == 200
    public = client.get(f"/api/v1/stores/{A}/products/{product['id']}").json()
    assert [item["id"] for item in public["images"]] == [second["id"], first["id"]]
    for item in public["images"]:
        image = client.get(item["url"])
        assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg"
        assert image.headers["x-content-type-options"] == "nosniff"
        assert Image.open(io.BytesIO(image.content)).format == "JPEG"
    assert attach(client, product, [first["id"]], response.json()["version"]).status_code == 200
    assert client.get(public_url(product, second["id"])).status_code == 404
    # Removing association is recoverable: media file itself remains protected and available.
    assert (
        client.get(base() + f"/media/{second['id']}/content", headers=headers(client)).status_code
        == 200
    )


def test_media_cross_tenant_preview_upload_modify_and_association(client):
    product = setup_product(client)
    own = upload(client).json()
    foreign = upload(client, B, "merchant-b").json()
    assert attach(client, product, [foreign["id"]]).status_code == 404
    for tenant in (A, B):
        assert (
            client.get(
                base(tenant) + f"/media/{own['id']}/content", headers=headers(client, "merchant-b")
            ).status_code
            == 404
        )
    assert client.get(base() + f"/media/{own['id']}/content").status_code == 401
    assert upload(client, A, "merchant-b").status_code == 404
    assert (
        client.patch(
            base(B) + f"/media/{own['id']}",
            headers=headers(client, "merchant-b"),
            json={"status": "ARCHIVED", "expected_version": 1},
        ).status_code
        == 404
    )
    assert client.get(public_url(product, own["id"], B)).status_code == 404


def test_store_product_and_media_status_all_guard_public_image(client):
    product = setup_product(client, published=False)
    media = upload(client).json()
    response = attach(client, product, [media["id"]])
    assert response.status_code == 200
    url = public_url(product, media["id"])
    assert client.get(url).status_code == 404
    assert (
        client.put(
            base() + "/store",
            headers=headers(client),
            json={"name": "图片店", "expected_version": 1, "published": True},
        ).status_code
        == 200
    )
    assert client.get(url).status_code == 200
    assert (
        client.patch(
            base() + f"/media/{media['id']}",
            headers=headers(client),
            json={"status": "ARCHIVED", "expected_version": 1},
        ).status_code
        == 200
    )
    assert client.get(url).status_code == 404
    assert client.get(f"/api/v1/stores/{A}/products/{product['id']}").json()["images"] == []
    assert (
        client.patch(
            base() + f"/media/{media['id']}",
            headers=headers(client),
            json={"status": "ACTIVE", "expected_version": 2},
        ).status_code
        == 200
    )
    assert client.get(url).status_code == 200
    payload = {
        k: v for k, v in product.items() if k not in {"id", "version", "price_label", "images"}
    }
    assert (
        client.put(
            base() + f"/products/{product['id']}",
            headers=headers(client),
            json=payload | {"status": "ARCHIVED", "expected_version": response.json()["version"]},
        ).status_code
        == 200
    )
    assert client.get(url).status_code == 404


def test_logo_is_separate_and_cross_tenant_logo_rejected(client):
    product = setup_product(client)
    logo = upload(client, purpose="LOGO").json()
    assert attach(client, product, [logo["id"]]).status_code == 404
    assert (
        client.put(
            base() + "/store",
            headers=headers(client),
            json={"name": "Logo店", "expected_version": 1, "logo_media_id": logo["id"]},
        ).status_code
        == 200
    )
    public = client.get(f"/api/v1/stores/{A}").json()
    assert client.get(public["logo_url"]).status_code == 200
    assert "logo_media_id" not in public
    foreign = upload(client, B, "merchant-b", purpose="LOGO").json()
    assert (
        client.put(
            base() + "/store",
            headers=headers(client),
            json={"name": "bad", "expected_version": 2, "logo_media_id": foreign["id"]},
        ).status_code
        == 404
    )
    assert (
        client.put(
            base() + "/store",
            headers=headers(client),
            json={"name": "Logo店", "expected_version": 2, "logo_media_id": None},
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/stores/{A}/logo").status_code == 404


def test_upload_idempotency_and_concurrency(client, pg_settings):
    key = str(uuid4())
    with ThreadPoolExecutor(5) as pool:
        responses = list(pool.map(lambda _: upload(client, key=key), range(5)))
    assert all(r.status_code == 201 for r in responses)
    assert len({r.json()["id"] for r in responses}) == 1
    assert upload(client, key=key, data=picture("blue")).status_code == 409
    assert len(list(pg_settings.media_root.glob("*.jpg"))) == 1


def test_image_normalization_removes_metadata_and_resizes(client):
    exif = Image.Exif()
    exif[0x010E] = "synthetic private metadata"
    result = upload(
        client, data=picture(size=(2000, 1000), fmt="JPEG", exif=exif), mime="image/jpeg"
    )
    assert result.status_code == 201
    assert result.json()["width"] == 1600 and result.json()["height"] == 800
    assert not {"storage_key", "owner_id", "sha256"} & result.json().keys()
    image = client.get(base() + f"/media/{result.json()['id']}/content", headers=headers(client))
    normalized = Image.open(io.BytesIO(image.content))
    assert not normalized.getexif()
    assert b"synthetic private metadata" not in image.content


@pytest.mark.parametrize(
    "data,mime,code",
    [
        (b"<svg><script/></svg>", "image/svg+xml", 415),
        (b"not a png", "image/png", 422),
        (b"", "image/png", 413),
        (b"x" * (MAX_UPLOAD + 1), "image/png", 413),
        (b"<!doctype html>", "image/png", 422),
    ],
    ids=["svg", "garbage", "empty", "oversize", "html"],
)
def test_reject_invalid_images_without_files(client, pg_settings, data, mime, code):
    assert upload(client, data=data, mime=mime).status_code == code
    assert not list(pg_settings.media_root.glob("*.jpg"))


def test_reject_oversized_decoded_image_and_animation(client):
    assert upload(client, data=picture(size=(4000, 3100))).status_code == 422
    output = io.BytesIO()
    first, second = Image.new("RGB", (16, 16), "red"), Image.new("RGB", (16, 16), "blue")
    first.save(output, "WEBP", save_all=True, append_images=[second], duration=100, loop=0)
    assert upload(client, data=output.getvalue(), mime="image/webp").status_code == 422


def test_image_order_limit_duplicates_and_version(client):
    product = setup_product(client)
    media = upload(client).json()
    assert attach(client, product, [media["id"], media["id"]]).status_code == 422
    assert attach(client, product, [str(uuid4()) for _ in range(9)]).status_code == 422
    assert attach(client, product, [media["id"]]).status_code == 200
    assert attach(client, product, []).status_code == 409


def test_commit_failure_removes_only_new_files(client, pg_settings):
    existing = upload(client).json()

    def fail(session):
        raise SQLAlchemyError("synthetic commit failure")

    event.listen(Session, "before_commit", fail)
    try:
        assert upload(client, data=picture("green")).status_code == 503
    finally:
        event.remove(Session, "before_commit", fail)
    files = list(pg_settings.media_root.glob("*.jpg"))
    assert len(files) == 1 and files[0].stem == existing["id"]
    engine = build_engine(pg_settings)
    try:
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(MediaObject)) == 1
    finally:
        engine.dispose()


def test_composite_media_foreign_key(client, pg_settings):
    product = setup_product(client)
    foreign = upload(client, B, "merchant-b").json()
    engine = build_engine(pg_settings)
    try:
        with pytest.raises(IntegrityError):
            with Session(engine) as session, session.begin():
                session.add(
                    ProductMedia(
                        tenant_id=UUID(A),
                        product_id=UUID(product["id"]),
                        media_id=UUID(foreign["id"]),
                        sort_order=0,
                    )
                )
                session.flush()
    finally:
        engine.dispose()


def test_missing_file_and_bad_uuid_are_safe(client, pg_settings):
    media = upload(client).json()
    path = pg_settings.media_root / (media["id"] + ".jpg")
    path.unlink()  # This fixture contains only its own synthetic image.
    response = client.get(base() + f"/media/{media['id']}/content", headers=headers(client))
    assert response.status_code == 404 and str(pg_settings.media_root) not in response.text
    assert (
        client.get(base() + "/media/not-a-uuid/content", headers=headers(client)).status_code == 422
    )
