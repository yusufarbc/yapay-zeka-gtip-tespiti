import json
import base64
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Any
from pydantic import BaseModel
from api.config import settings

class UserSession(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str # "broker_assistant" | "senior_broker" | "admin"
    domain: Optional[str] = None # Google Workspace Enterprise Domain (e.g., sirketiniz.com)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    try:
        from jose import jwt
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    except ImportError:
        payload = data.copy()
        payload_bytes = json.dumps(payload).encode('utf-8')
        encoded_payload = base64.urlsafe_b64encode(payload_bytes).decode('utf-8').rstrip("=")
        signature = hmac.new(settings.JWT_SECRET_KEY.encode('utf-8'), encoded_payload.encode('utf-8'), hashlib.sha256).hexdigest()
        return f"{encoded_payload}.{signature}"

def decode_access_token(token: str) -> Optional[UserSession]:
    """
    Hem Kurumsal JWT jetonlarını hem de Google Workspace OpenID Connect (Google OAuth 2.0) jetonlarını doğrular.
    """
    try:
        # 1. Google OAuth 2.0 / OpenID Connect ID Token Yetkilendirme Kontrolü
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            
            # Google ID Token Doğrulama
            id_info = id_token.verify_oauth2_token(token, google_requests.Request())
            if id_info and "email" in id_info:
                email = id_info["email"]
                full_name = id_info.get("name", email.split("@")[0].title())
                domain = id_info.get("hd") # Google Workspace Kurumsal Etki Alanı
                user_id = id_info.get("sub", f"google_{email.split('@')[0]}")
                return UserSession(
                    user_id=user_id,
                    email=email,
                    full_name=full_name,
                    role="senior_broker",
                    domain=domain
                )
        except Exception:
            pass

        # 2. Standart Kurumsal JWT Token Çözümleme
        try:
            from jose import jwt
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        except ImportError:
            parts = token.split(".")
            if len(parts) != 2:
                return None
            encoded_payload, signature = parts
            expected_sig = hmac.new(settings.JWT_SECRET_KEY.encode('utf-8'), encoded_payload.encode('utf-8'), hashlib.sha256).hexdigest()
            if signature != expected_sig:
                return None
            padding = "=" * (4 - len(encoded_payload) % 4)
            payload_bytes = base64.urlsafe_b64decode(encoded_payload + padding)
            payload = json.loads(payload_bytes.decode('utf-8'))

        user_id: str = payload.get("sub", payload.get("user_id"))
        email: str = payload.get("email")
        full_name: str = payload.get("full_name", email.split("@")[0].title() if email else "")
        role: str = payload.get("role", "customs_broker")
        if not email:
            return None
        return UserSession(user_id=user_id or "user_1", email=email, full_name=full_name, role=role)
    except Exception:
        return None

def get_current_user_session(request: Any) -> UserSession:
    """
    Google Workspace OAuth 2.0 & GCP IAP Kimlik Doğrulama Katmanı:
    1. Google OAuth 2.0 / JWT Token (Authorization: Bearer <token>)
    2. GCP / Google Workspace Identity-Aware Proxy (x-goog-authenticated-user-email & x-goog-iap-jwt-assertion)
    3. Dinamik Kurumsal İstek Üstbilgileri (X-User-Email, X-User-Role)
    4. Anonim Sistem Oturumu Fallback (Gerçekçi jenerik etki alanı)
    """
    try:
        # 1. Bearer Token (Google OAuth 2.0 veya JWT)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            session = decode_access_token(token)
            if session:
                return session

        # 2. GCP Cloud IAP (Identity-Aware Proxy) Google Workspace SSO
        iap_jwt = request.headers.get("x-goog-iap-jwt-assertion")
        if iap_jwt:
            session = decode_access_token(iap_jwt)
            if session:
                return session

        iap_email = request.headers.get("x-goog-authenticated-user-email")
        if iap_email:
            email = iap_email.replace("accounts.google.com:", "").strip()
            domain = email.split("@")[1] if "@" in email else None
            role = request.headers.get("X-User-Role", "senior_broker")
            return UserSession(
                user_id=f"gcp_{email.split('@')[0]}",
                email=email,
                full_name=email.split('@')[0].replace(".", " ").title(),
                role=role,
                domain=domain
            )

        # 3. Özel HTTP Üstbilgileri (Client / UI Entegrasyonu)
        custom_email = request.headers.get("X-User-Email")
        if custom_email:
            role = request.headers.get("X-User-Role", "customs_broker")
            domain = custom_email.split("@")[1] if "@" in custom_email else None
            return UserSession(
                user_id=f"user_{custom_email.split('@')[0]}",
                email=custom_email.strip(),
                full_name=custom_email.split('@')[0].replace(".", " ").title(),
                role=role,
                domain=domain
            )
    except Exception:
        pass

    # 4. Fallback: Dinamik İstek Bağlamı (Uydurma şahıs ismi kullanılmaz)
    client_host = getattr(getattr(request, "client", None), "host", "127.0.0.1")
    return UserSession(
        user_id=f"client_{client_host.replace('.', '_')}",
        email=f"musavir@{settings.GCP_PROJECT_ID}.google",
        full_name="Gümrük Müşaviri Oturumu",
        role="customs_broker",
        domain=f"{settings.GCP_PROJECT_ID}.google"
    )
