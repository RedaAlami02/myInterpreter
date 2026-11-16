"""Service-key validation and headers for Supabase REST/RPC calls.

Legacy service_role keys are JWTs and work in both `apikey` and
`Authorization: Bearer`. New `sb_secret_...` keys are sent in `apikey` only;
sending them as a Bearer token yields `401 Invalid API key`.
"""
import base64
import json


class ServiceKeyError(ValueError):
    pass


def service_headers(key):
    if not isinstance(key, str):
        raise ServiceKeyError("MISSING_SERVICE_ROLE_KEY")
    key = key.strip()
    if not key:
        raise ServiceKeyError("MISSING_SERVICE_ROLE_KEY")
    if key.startswith("sb_publishable_"):
        raise ServiceKeyError("PUBLISHABLE_KEY_IS_NOT_A_SERVICE_KEY")
    if key.startswith("sb_secret_"):
        return {"apikey": key}
    if key.startswith("eyJ"):
        parts = key.split(".")
        if len(parts) != 3:
            raise ServiceKeyError("INVALID_SERVICE_KEY_FORMAT")
        try:
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        except Exception:
            raise ServiceKeyError("INVALID_SERVICE_KEY_FORMAT") from None
        if not isinstance(claims, dict) or claims.get("role") != "service_role":
            raise ServiceKeyError("SERVICE_KEY_ROLE_IS_NOT_SERVICE_ROLE")
        return {"apikey": key, "Authorization": "Bearer " + key}
    raise ServiceKeyError("INVALID_SERVICE_KEY_FORMAT")
