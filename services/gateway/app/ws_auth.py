"""WebSocket-session signed-token auth.

Tokens are minted by `GET /sessions/{id}/ws_token` (REST, basicauth +
same-origin) and verified by the WS endpoint before `accept()`. Signing
key is `INTERNAL_RPC_SECRET` — the same key used for gateway↔analysis
RPC. Tokens are short-lived (default 5 min) and bind to a specific
session_id so they can't be reused across sessions.

Why not JWT? We control both ends, payload is two fields, and
constant-time comparison via `hmac.compare_digest` is enough. The
extra surface area of a JWT lib is wasted here.

Disable enforcement by setting `WS_AUTH_REQUIRED=0` (the dev default,
so existing local flows aren't broken until the frontend learns to
fetch a token).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from uuid import UUID


_DEFAULT_TTL_SECONDS = 300


def _secret() -> bytes:
    raw = os.getenv("INTERNAL_RPC_SECRET", "")
    if not raw:
        raise RuntimeError(
            "INTERNAL_RPC_SECRET is required for WS auth — set it in .env"
        )
    return raw.encode()


def is_required() -> bool:
    """When `WS_AUTH_REQUIRED=1`, the WS endpoint rejects tokenless
    connections. Default 0 so local dev / smoke runs still work."""
    return os.getenv("WS_AUTH_REQUIRED", "0") == "1"


def mint_token(session_id: UUID, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> tuple[str, int]:
    """Return `(token, expires_in_seconds)`.

    Token shape: `<exp>.<sig_b64>` where `sig = HMAC-SHA256(secret, "<session_id>|<exp>")`.
    Using URL-safe base64 keeps it safe in a query parameter.
    """
    exp = int(time.time()) + ttl_seconds
    msg = f"{session_id}|{exp}".encode()
    sig = hmac.new(_secret(), msg, hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{exp}.{encoded}", ttl_seconds


def verify_token(session_id: UUID, token: str | None) -> bool:
    """True if `token` is a valid, unexpired signature for `session_id`."""
    if not token:
        return False
    try:
        exp_str, sig_b64 = token.split(".", 1)
        exp = int(exp_str)
    except (ValueError, AttributeError):
        return False
    if exp < time.time():
        return False
    expected = hmac.new(_secret(), f"{session_id}|{exp}".encode(), hashlib.sha256).digest()
    expected_b64 = base64.urlsafe_b64encode(expected).rstrip(b"=").decode()
    return hmac.compare_digest(expected_b64, sig_b64)
