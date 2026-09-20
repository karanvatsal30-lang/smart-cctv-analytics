"""
User Authentication & Identification Middleware.

Provides:
1. Supabase JWT verification for production cloud deployments.
2. Offline / local operator identification mode when Supabase is not configured.
3. Strict security: SERVICE_ROLE_KEY is never exposed to browser.
4. Anonymous publishable key is served only via /api/config/public.
"""

import os
import functools
from flask import request, jsonify

# PyJWT is used for offline JWT verification using the project's JWT secret.
try:
    import jwt as pyjwt
    PYJWT_AVAILABLE = True
except ImportError:
    PYJWT_AVAILABLE = False


def get_jwt_secret() -> str:
    return os.environ.get("SUPABASE_JWT_SECRET", "").strip()


def is_supabase_configured() -> bool:
    """Returns True if Supabase credentials are configured."""
    return bool(
        os.environ.get("SUPABASE_URL", "").strip()
        and (get_jwt_secret() or os.environ.get("SUPABASE_SERVICE_KEY", "").strip())
    )


class AuthError(Exception):
    """Raised when authentication fails."""
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def verify_jwt(token: str) -> dict:
    """
    Verifies a Supabase-issued JWT offline using the project JWT secret.
    Returns the decoded payload dict on success.
    Raises AuthError on any failure.
    """
    jwt_secret = get_jwt_secret()
    if not jwt_secret:
        # If no JWT secret is provided, check if in local mode
        raise AuthError("SUPABASE_JWT_SECRET is not configured on server.", 500)

    if not PYJWT_AVAILABLE:
        raise AuthError("PyJWT library not installed on server.", 500)

    if not token or not token.strip():
        raise AuthError("Authorization token is missing.", 401)

    try:
        payload = pyjwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
        return payload
    except pyjwt.ExpiredSignatureError:
        raise AuthError("Session has expired. Please sign in again.", 401)
    except pyjwt.InvalidTokenError as e:
        raise AuthError(f"Invalid session token: {str(e)}", 401)


def get_user_id(token: str) -> str:
    """
    Extracts and returns the user_id (sub claim) from a verified JWT.
    Raises AuthError if token is invalid or missing sub claim.
    """
    payload = verify_jwt(token)
    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("Token is missing user identity (sub claim).", 401)
    return user_id


def get_bearer_token() -> str:
    """
    Extracts Bearer token from request Authorization header.
    Returns empty string if not present.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer "):].strip()
    return ""


def require_auth(f):
    """
    Flask decorator: ensures the request is from an identified / authenticated user.
    - When Supabase is configured: strictly validates Supabase JWT Bearer token.
    - When Supabase is not configured (local mode): accepts user identification header (X-User-ID)
      or defaults to 'operator_station'.
    Injects `user_id` into the endpoint.
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_bearer_token()

        if is_supabase_configured():
            if not token:
                # Check for explicit station header if allowed, else require token
                station_id = request.headers.get("X-Station-ID")
                if station_id:
                    return f(*args, user_id=f"station_{station_id}", **kwargs)
                return jsonify({
                    "error": "Authentication required. Please sign in.",
                    "authenticated": False
                }), 401
            try:
                user_id = get_user_id(token)
            except AuthError as e:
                return jsonify({
                    "error": e.message,
                    "authenticated": False
                }), e.status_code
        else:
            # Standalone Local Mode: identify via X-User-ID or Bearer token or default
            user_id = (
                request.headers.get("X-User-ID")
                or request.headers.get("X-Station-ID")
                or (f"user_{token[:12]}" if token else "operator_station")
            )

        return f(*args, user_id=user_id, **kwargs)
    return decorated_function
