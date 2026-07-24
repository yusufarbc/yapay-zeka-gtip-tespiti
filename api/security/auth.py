import json
import base64
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
from api.config import settings

class UserSession(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str # "broker_assistant" | "senior_broker" | "admin"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    try:
        from jose import jwt
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    except ImportError:
        # Fallback simple token encoder if python-jose is not yet pip-installed
        payload = data.copy()
        payload_bytes = json.dumps(payload).encode('utf-8')
        encoded_payload = base64.urlsafe_b64encode(payload_bytes).decode('utf-8').rstrip("=")
        signature = hmac.new(settings.JWT_SECRET_KEY.encode('utf-8'), encoded_payload.encode('utf-8'), hashlib.sha256).hexdigest()
        return f"{encoded_payload}.{signature}"

def decode_access_token(token: str) -> Optional[UserSession]:
    try:
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
        full_name: str = payload.get("full_name", "")
        role: str = payload.get("role", "broker_assistant")
        if not email:
            return None
        return UserSession(user_id=user_id or "user_1", email=email, full_name=full_name, role=role)
    except Exception:
        return None
