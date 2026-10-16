from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from local_shop.config import Settings
from local_shop.identity import require_local
from local_shop.proxy_source import auth_source
from starlette.requests import Request


def request(peer, headers=()):
    return Request(
        {
            "type": "http",
            "client": (peer, 1234),
            "headers": [(k.encode(), v.encode()) for k, v in headers],
        }
    )


def test_explicit_source_only_and_no_peer_mutation():
    config = SimpleNamespace(auth_trusted_proxy_ips="127.0.0.1")
    r = request("127.0.0.1", [("x-local-shop-client-ip", "192.0.2.1")])
    assert auth_source(config, r) == "192.0.2.1"
    assert r.client.host == "127.0.0.1"
    r = request(
        "192.0.2.2", [("x-local-shop-client-ip", "127.0.0.1"), ("x-forwarded-for", "127.0.0.1")]
    )
    assert auth_source(config, r) == "192.0.2.2"
    with pytest.raises(HTTPException):
        require_local(r)
    assert (
        auth_source(
            SimpleNamespace(auth_trusted_proxy_ips=""),
            request("127.0.0.1", [("x-local-shop-client-ip", "192.0.2.1")]),
        )
        == "127.0.0.1"
    )


@pytest.mark.parametrize(
    "values", [[], ["bad"], ["192.0.2.1,192.0.2.2"], ["fe80::1%eth0"], ["192.0.2.1", "192.0.2.2"]]
)
def test_invalid_or_duplicate_is_conservative(values):
    assert (
        auth_source(
            SimpleNamespace(auth_trusted_proxy_ips="127.0.0.1"),
            request("127.0.0.1", [("x-local-shop-client-ip", v) for v in values]),
        )
        == "127.0.0.1"
    )


@pytest.mark.parametrize("value", ["*", "127.0.0.0/8", "localhost", "127.0.0.1,", "fe80::1%eth0"])
def test_config_rejects_unbounded_or_invalid_trust(value):
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://test@localhost/test",
            app_secret_key="synthetic-only-varied-0123456789abcdef",
            auth_trusted_proxy_ips=value,
        )


def test_proxy_mode_cannot_enable_demo():
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://test@localhost/test",
            app_secret_key="synthetic-only-varied-0123456789abcdef",
            auth_trusted_proxy_ips="127.0.0.1",
            dev_auth_enabled=True,
        )
