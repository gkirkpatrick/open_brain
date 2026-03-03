import hmac

from fastapi import HTTPException, Request

from open_brain.config import settings


def verify_access_key(request: Request):
    """Verify the bearer token or x-brain-key header."""
    if not settings.open_brain_access_key:
        return  # No key configured, allow all (dev mode)

    # Check Authorization header
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if hmac.compare_digest(token, settings.open_brain_access_key):
            return

    # Check x-brain-key header
    brain_key = request.headers.get("x-brain-key", "")
    if brain_key and hmac.compare_digest(brain_key, settings.open_brain_access_key):
        return

    # Check query parameter
    key_param = request.query_params.get("key", "")
    if key_param and hmac.compare_digest(key_param, settings.open_brain_access_key):
        return

    raise HTTPException(status_code=401, detail="Invalid or missing access key")
