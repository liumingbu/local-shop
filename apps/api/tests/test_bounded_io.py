import asyncio
import secrets

import pytest
from fastapi import HTTPException
from local_shop.config import Settings
from local_shop.image_store import MAX_UPLOAD, read_bounded_image
from pydantic import ValidationError
from starlette.requests import ClientDisconnect


class Stream:
    def __init__(self, chunks=(), delay=0, headers=None, disconnect=False):
        self.chunks = chunks
        self.delay = delay
        self.headers = headers or {}
        self.disconnect = disconnect
        self.reads = 0

    async def stream(self):
        for chunk in self.chunks:
            self.reads += 1
            await asyncio.sleep(self.delay)
            yield chunk
        if self.disconnect:
            raise ClientDisconnect()


def test_image_receipt_uses_total_deadline_not_per_chunk():
    stream = Stream([b"x"] * 20, delay=0.015)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(read_bounded_image(stream, 0.05))
    assert caught.value.status_code == 408 and caught.value.detail == "IMAGE_UPLOAD_TIMEOUT"
    assert stream.reads < 20


@pytest.mark.parametrize(
    "length,status",
    [("invalid", 400), ("-1", 400), ("９", 400), (str(MAX_UPLOAD + 1), 413), ("9" * 100, 413)],
)
def test_invalid_length_rejected_before_read(length, status):
    stream = Stream([b"x"], headers={"content-length": length})
    with pytest.raises(HTTPException) as caught:
        asyncio.run(read_bounded_image(stream, 1))
    assert caught.value.status_code == status and stream.reads == 0


def test_missing_or_lying_length_cannot_bypass_stream_limit():
    for headers in ({}, {"content-length": "1"}):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(read_bounded_image(Stream([b"x" * MAX_UPLOAD, b"x"], headers=headers), 1))
        assert caught.value.status_code == 413


def test_disconnect_sanitized_and_normal_chunking_preserved():
    assert asyncio.run(read_bounded_image(Stream([b"one", b"two"]), 1)) == b"onetwo"
    with pytest.raises(HTTPException) as caught:
        asyncio.run(read_bounded_image(Stream([b"x"], disconnect=True), 1))
    assert caught.value.detail == "IMAGE_UPLOAD_INTERRUPTED"


@pytest.mark.parametrize(
    "patch",
    [
        {"media_receive_timeout_seconds": 0},
        {"media_receive_timeout_seconds": float("inf")},
        {"db_statement_timeout_ms": 0},
        {"db_lock_timeout_ms": -1},
        {"db_pool_timeout_seconds": 0},
    ],
)
def test_unbounded_timeout_configuration_rejected(patch):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://synthetic@localhost/test",
            app_secret_key=secrets.token_urlsafe(32),
            **patch,
        )
