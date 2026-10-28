"""Supabase JWT verification.

Authentication is exclusively based on Supabase-issued access tokens.  The
backend never hashes passwords, never issues its own JWTs and never stores
credentials in ``public`` tables.

Three verification paths exist:

1. ``SUPABASE_JWT_SECRET`` is set → offline HS256 verification against the
   secret (audience ``authenticated``).  Fast, no network dependency, and the
   default in production.
2. If the token signature fails the HS256 check (or the secret is unset) →
   verify against the project's JWKS endpoint via ``kid``.  This covers new
   Supabase projects using asymmetric signing keys (ES256/RS256), whose
   tokens the legacy HS256 JWT secret can neither parse-verify nor sign.
3. ``SUPABASE_JWT_SECRET`` is unset and JWKS verification is unusable →
   server-side validation against GoTrue (``GET /auth/v1/user``).  Kept so
   local/dev installs without the secret still work; it always makes a
   network round trip to confirm the token is live.

Only which path verified the token is logged — never the token itself.
"""
from typing import Any

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from app.core.config import settings
from app.core.logging import get_logger
from app.middleware.request_context import current_user

logger = get_logger("auth")

bearer_scheme = HTTPBearer(auto_error=False)

# JWKS cache: (fetched_at_monotonic, keys). Refreshed at most once per 10 min
# so a rotated signing key keeps working without a per-request fetch.
_JWKS_TTL_SECONDS = 600
_jwks_cache: tuple[float, list[dict[str, Any]]] | None = None


def _get_jwks() -> list[dict[str, Any]]:
    """Fetch (and cache) the Supabase project's JWT signing keys."""
    import time

    global _jwks_cache
    if _jwks_cache is not None and (time.monotonic() - _jwks_cache[0]) < _JWKS_TTL_SECONDS:
        return _jwks_cache[1]
    url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
    headers = {"apikey": settings.SUPABASE_ANON_KEY} if settings.SUPABASE_ANON_KEY else {}
    resp = httpx.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    keys = [k for k in resp.json().get("keys", []) if isinstance(k, dict)]
    if not keys:
        raise ValueError("JWKS endpoint returned no keys")
    _jwks_cache = (time.monotonic(), keys)
    return keys


class AuthError(HTTPException):
    """Raised for any auth failure with a consistent 401 payload."""

    def __init__(self, detail: str = "Not authenticated") -> None:
        super().__init__(status_code=401, detail=detail)


def _verify_with_jwks(token: str) -> dict[str, Any] | None:
    """Verify the token against the project's JWKS signing keys.

    Covers Supabase projects using asymmetric signing keys (ES256/RS256).
    Returns None when verification is not possible so callers can fall back
    to the next strategy instead of treating this as a hard failure.
    """
    try:
        keys = _get_jwks()
    except (httpx.HTTPError, ValueError):
        logger.warning("auth jwks_unavailable")
        return None
    try:
        claims = jwt.decode(
            token,
            {"keys": keys},
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            options={"verify_at_hash": False},
        )
        return dict(claims)
    except ExpiredSignatureError:
        raise AuthError("Token has expired")
    except JWTError:
        return None


def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase-issued access token and return its claims."""
    if settings.SUPABASE_JWT_SECRET:
        try:
            claims = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
                audience="authenticated",
            )
            logger.info("auth verification=local_hs256")
            return dict(claims)
        except ExpiredSignatureError:
            # An expired token fails the same way regardless of signing key —
            # report expiry directly (jose checks exp before signature).
            logger.info("auth verification=local_hs256 expired_token")
            raise AuthError("Token has expired")
        except JWTError:
            # Most common cause: the project now signs with asymmetric
            # keys (ES256/RS256), which the legacy HS256 secret cannot
            # verify — jose raises "The specified alg value is not allowed".
            claims = _verify_with_jwks(token)
            if claims is not None:
                logger.info("auth verification=jwks_asymmetric")
                return claims
            logger.info("auth verification=local_hs256 malformed_token")
            raise AuthError("Invalid token")

    url = f"{settings.SUPABASE_URL}/auth/v1/user"
    headers = {
        "apikey": settings.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {token}",
    }
    try:
        resp = httpx.get(url, headers=headers, timeout=20)
    except httpx.HTTPError:
        logger.error("auth verification=go_true unavailable")
        raise HTTPException(status_code=503, detail="Auth service unavailable")
    if resp.status_code != 200:
        logger.info("auth verification=go_true invalid_token")
        raise AuthError("Invalid token")

    logger.info("auth verification=go_true")
    data = resp.json()
    return {
        "sub": data.get("id"),
        "email": data.get("email"),
        "aud": "authenticated",
        "app_metadata": data.get("app_metadata"),
        "user_metadata": data.get("user_metadata"),
    }


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """FastAPI dependency: require a valid Supabase access token.

    Returns the verified JWT claims (user id is ``claims["sub"]``). Raises 401
    when the Authorization header is missing or the token is invalid/expired.
    """
    if credentials is None or not credentials.credentials:
        raise AuthError("Not authenticated")

    claims = verify_supabase_token(credentials.credentials)
    current_user.set(claims)
    return claims


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """FastAPI dependency: like get_current_user but returns just the user id."""
    return get_current_user(credentials).get("sub")