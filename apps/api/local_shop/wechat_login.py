"""Fixed HTTPS provider boundary. No session_key persistence, credential logs or redirects."""

import base64
import http.client
import json
import re
import socket
import ssl
import time
from urllib.parse import urlencode

from fastapi import HTTPException


def exchange(settings, code):
    if not settings.wechat_login_enabled:
        raise HTTPException(503, "WECHAT_LOGIN_NOT_CONFIGURED")
    connection = http.client.HTTPSConnection(
        "api.weixin.qq.com", timeout=5, context=ssl.create_default_context()
    )
    connection.set_debuglevel(0)
    try:
        deadline = time.monotonic() + 10
        query = urlencode(
            {
                "appid": settings.wechat_appid,
                "secret": settings.wechat_app_secret.get_secret_value(),
                "js_code": code,
                "grant_type": "authorization_code",
            }
        )
        connection.request(
            "GET",
            "/sns/jscode2session?" + query,
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
        )
        transport_socket = connection.sock
        response = connection.getresponse()
        if response.status != 200:
            raise HTTPException(503, "WECHAT_PROVIDER_UNAVAILABLE")
        body = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            if transport_socket:
                transport_socket.settimeout(min(5, remaining))
            chunk = response.read1(min(1024, 8193 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > 8192:
                raise ValueError()
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError()
        if value.get("errcode"):
            if value["errcode"] in (40029, 40163):
                raise HTTPException(401, "WECHAT_CODE_INVALID")
            if value["errcode"] == 45011:
                raise HTTPException(429, "WECHAT_RATE_LIMITED")
            raise HTTPException(503, "WECHAT_PROVIDER_UNAVAILABLE")
        openid, key = value.get("openid"), value.get("session_key")
        if (
            not isinstance(openid, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", openid)
            or not isinstance(key, str)
            or len(key) > 256
        ):
            raise ValueError()
        if len(base64.b64decode(key, validate=True)) != 16:
            raise ValueError()
        return openid
    except HTTPException:
        raise
    except (OSError, socket.timeout, http.client.HTTPException, ValueError, TypeError):
        raise HTTPException(503, "WECHAT_PROVIDER_UNAVAILABLE") from None
    finally:
        connection.close()
