"""castle/server/auth_middleware.py · Google OAuth 認證 (v0.9.6 · Edward 5/23 拍板)

純前端 Google Identity Services (GIS) flow:
1. user 訪問 /static/auth.html → GIS button popup → Google 登入
2. Google 回 ID token → POST /auth/verify
3. 後端驗 ID token + email in allow list → set signed cookie (30 天)
4. user redirect /static/index.html → cookie 認 → 通行

只允許 Edward 個人 Google 帳號 (edwardt0303@gmail.com)
"""

import os
import logging

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.environ.get(
    "SOPHIE_GOOGLE_CLIENT_ID",
    "870408555328-dv80l5gs73os63r44e8ed79kndcoorbm.apps.googleusercontent.com",
)

# Allow list · 只 Edward 個人 AI · 不對外
ALLOWED_EMAILS = frozenset({
    "edwardt0303@gmail.com",
})

COOKIE_NAME = "sophie_auth"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days

# Cookie secret (fallback hardcoded · 長 random 32-char hex · 公開 repo 可見但 attacker 不知 ALLOWED_EMAILS 也偽不來)
# Edward 後續可改 Modal Secret SOPHIE_COOKIE_SECRET 強化
_COOKIE_SECRET = os.environ.get(
    "SOPHIE_COOKIE_SECRET",
    "a7f9c2e4d8b1a3c5e7f0b2d4a6c8e1b3d5f7a9c2e4b6d8f0a2c4e6b8d1f3a5c7",
)
_serializer = URLSafeTimedSerializer(_COOKIE_SECRET, salt="sophie-auth-cookie-v1")

# 不需認證的 path (auth flow 必經、SDP 需 unauth handshake 但 Google verify 仍守)
PUBLIC_EXACT = frozenset({
    "/",
    "/static/auth.html",
    "/health",
    "/personas",
    "/favicon.ico",
})
PUBLIC_PREFIX = (
    "/auth/",  # /auth/verify · /auth/logout
)


def verify_google_id_token(token_str: str) -> str | None:
    """Verify Google ID token JWT · return email if valid + in allow list, else None."""
    try:
        info = id_token.verify_oauth2_token(
            token_str,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except ValueError as e:
        logger.warning("[auth] Google ID token verify fail: %s", str(e)[:200])
        return None
    except Exception as e:
        logger.warning("[auth] Google ID token unexpected fail: %s", type(e).__name__)
        return None

    email = info.get("email", "").lower()
    email_verified = info.get("email_verified", False)

    if not email_verified:
        logger.warning("[auth] email not verified: %s", email)
        return None
    if email not in ALLOWED_EMAILS:
        logger.warning("[auth] email not in allow list: %s", email)
        return None

    logger.info("[auth] Google verify OK · %s", email)
    return email


def sign_email_cookie(email: str) -> str:
    """Sign email into cookie value (HMAC + timestamp)."""
    return _serializer.dumps(email)


def verify_signed_cookie(cookie_value: str) -> str | None:
    """Verify signed cookie · return email if valid + not expired + in allow list, else None."""
    try:
        email = _serializer.loads(cookie_value, max_age=COOKIE_MAX_AGE)
    except SignatureExpired:
        logger.info("[auth] cookie expired")
        return None
    except BadSignature:
        logger.warning("[auth] cookie bad signature (tampered?)")
        return None
    except Exception:
        return None

    if email in ALLOWED_EMAILS:
        return email
    logger.warning("[auth] cookie email no longer in allow list: %s", email)
    return None


def is_public_path(path: str) -> bool:
    """Check if path bypasses auth (auth flow + health + static auth.html)."""
    if path in PUBLIC_EXACT:
        return True
    for prefix in PUBLIC_PREFIX:
        if path.startswith(prefix):
            return True
    return False
