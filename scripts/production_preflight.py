"""Fail-closed release gate. It does not deploy, change accounts, or connect to production."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from local_shop.config import Settings  # noqa: E402
from pydantic import ValidationError  # noqa: E402


def main():
    try:
        settings = Settings()
    except ValidationError:
        print("BLOCKED_CONFIGURATION: check protected configuration; values suppressed")
        return 2
    if settings.app_env != "production" or settings.dev_auth_enabled:
        print("BLOCKED_ENVIRONMENT: production requires real identity, never a demo session")
        return 2
    if settings.api_host != "127.0.0.1":
        print("BLOCKED_BINDING: candidate service must bind the loopback API behind the proxy")
        return 2
    # Deliberate hard stop, not a user-settable flag that can bless incomplete authentication.
    print(
        "BLOCKED_REAL_WECHAT_ACCEPTANCE: identity code exists; "
        "real provider/device/privacy acceptance is pending; "
        "do not publish this development build"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
