from __future__ import annotations

import hashlib
import hmac
import time


def verify_bearer_token(header_value: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    if not header_value:
        return False
    if header_value.lower().startswith("bearer "):
        token = header_value[7:].strip()
    else:
        token = header_value.strip()
    return hmac.compare_digest(token, expected)


def verify_slack_signature(
    *,
    signing_secret: str | None,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
) -> bool:
    if not signing_secret:
        return True
    if not timestamp or not signature:
        return False
    try:
        request_ts = int(timestamp)
    except ValueError:
        return False
    if abs(int(time.time()) - request_ts) > 60 * 5:
        return False
    base = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    expected = "v0=" + hmac.new(signing_secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_github_signature(*, secret: str | None, signature: str | None, body: bytes) -> bool:
    if not secret:
        return True
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
