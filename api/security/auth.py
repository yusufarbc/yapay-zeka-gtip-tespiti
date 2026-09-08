"""JWT, Google OAuth ve yönetici yetkilendirme yardımcıları."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel

from api.config import settings


VALID_ROLES = {"customs_broker", "broker_assistant", "senior_broker", "admin"}


class UserSession(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    domain: Optional[str] = None


def _csv_values(raw: str) -> set[str]:
    return {value.strip().lower() for value in raw.split(",") if value.strip()}


def _session_from_internal_payload(payload: dict) -> Optional[UserSession]:
    email = str(payload.get("email") or "").strip().lower()
    if not email:
        return None
    role = str(payload.get("role") or "customs_broker")
    if role not in VALID_ROLES:
        return None
    return UserSession(
        user_id=str(payload.get("sub") or payload.get("user_id") or f"user_{email}"),
        email=email,
        full_name=str(payload.get("full_name") or email.split("@", 1)[0].title()),
        role=role,
        domain=email.rsplit("@", 1)[-1] if "@" in email else None,
    )


def _session_from_google_payload(payload: dict) -> Optional[UserSession]:
    email = str(payload.get("email") or "").strip().lower()
    verified = payload.get("email_verified")
    if not email or verified not in (True, "true", "True", "1", 1):
        return None

    email_domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    hosted_domain = str(payload.get("hd") or email_domain).lower()
    allowed_domains = _csv_values(settings.GOOGLE_WORKSPACE_DOMAINS)
    if allowed_domains and hosted_domain not in allowed_domains:
        return None

    if email in _csv_values(settings.ADMIN_EMAILS):
        role = "admin"
    elif email in _csv_values(settings.SENIOR_BROKER_EMAILS):
        role = "senior_broker"
    else:
        role = "customs_broker"

    return UserSession(
        user_id=str(payload.get("sub") or f"google_{email}"),
        email=email,
        full_name=str(payload.get("name") or email.split("@", 1)[0].title()),
        role=role,
        domain=hosted_domain or None,
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Kurumsal, süreli HS256 erişim tokenı üretir."""
    import jwt

    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[UserSession]:
    """Önce kurumsal JWT'yi, sonra audience-kilitli Google ID tokenını doğrular."""
    if not token:
        return None

    try:
        import jwt

        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        session = _session_from_internal_payload(payload)
        if session:
            return session
    except Exception:
        pass

    if not settings.GOOGLE_OAUTH_CLIENT_ID:
        return None
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        payload = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=settings.GOOGLE_OAUTH_CLIENT_ID,
        )
        return _session_from_google_payload(payload)
    except Exception:
        return None


def _decode_iap_token(token: str) -> Optional[UserSession]:
    """IAP assertion'ını yalnızca beklenen IAP audience'i yapılandırılmışsa doğrular."""
    if not token or not settings.IAP_AUDIENCE:
        return None
    try:
        import requests
        from google.auth import jwt

        response = requests.get("https://www.gstatic.com/iap/verify/public_key", timeout=5)
        response.raise_for_status()
        payload = jwt.decode(token, certs=response.json(), audience=settings.IAP_AUDIENCE)
        if payload.get("iss") != "https://cloud.google.com/iap":
            return None
        payload = dict(payload)
        payload["email_verified"] = True
        return _session_from_google_payload(payload)
    except Exception:
        return None


def get_current_user_session(request: Any) -> UserSession:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        session = decode_access_token(auth_header[7:].strip())
        if session:
            return session

    iap_session = _decode_iap_token(request.headers.get("x-goog-iap-jwt-assertion", ""))
    if iap_session:
        return iap_session

    if settings.ENVIRONMENT != "production":
        custom_email = request.headers.get("X-User-Email", "").strip().lower()
        if custom_email:
            requested_role = request.headers.get("X-User-Role", "customs_broker")
            role = requested_role if requested_role in VALID_ROLES else "customs_broker"
            return UserSession(
                user_id=f"user_{custom_email.split('@', 1)[0]}",
                email=custom_email,
                full_name=custom_email.split("@", 1)[0].replace(".", " ").title(),
                role=role,
                domain=custom_email.rsplit("@", 1)[-1] if "@" in custom_email else None,
            )

    if settings.ENVIRONMENT == "production" and not settings.ALLOW_PUBLIC_DEMO_ACCESS:
        raise HTTPException(status_code=401, detail="Geçerli bir kimlik doğrulama jetonu gereklidir.")

    client_host = getattr(getattr(request, "client", None), "host", "127.0.0.1")
    safe_host = str(client_host).replace(".", "_").replace(":", "_")
    return UserSession(
        user_id=f"demo_{safe_host}",
        email="demo-musavir@gtip.gov.tr",
        full_name="Gümrük Müşaviri (Canlı Demo)",
        role="customs_broker",
        domain="gtip.gov.tr",
    )


def require_admin_user(request: Any) -> UserSession:
    session = get_current_user_session(request)
    if session.role not in {"admin", "senior_broker"}:
        raise HTTPException(
            status_code=403,
            detail="Bu yönetimsel operasyon için yetkili kullanıcı gerekir.",
        )
    return session
