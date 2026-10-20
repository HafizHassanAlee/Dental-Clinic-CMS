import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import bcrypt
import jwt
from fastapi import Request
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.entities import AuditLog, User


COOKIE_ACCESS_TOKEN = "rumi_access_token"
COOKIE_CSRF_TOKEN = "rumi_csrf_token"
HEADER_CSRF_TOKEN = "X-CSRF-Token"


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def validate_password_strength(password: str) -> Optional[str]:
    if not password or len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one digit."
    return None


def create_access_token(
    user_id: int,
    role_name: str,
    token_version: int = 1,
    expires_minutes: Optional[int] = None,
) -> str:
    now = datetime.now(timezone.utc)
    exp_minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    payload = {
        "sub": str(user_id),
        "role": role_name,
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=exp_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except Exception:
        return None


def generate_csrf_token(user_id: int) -> str:
    nonce = secrets.token_hex(16)
    msg = f"{user_id}:{nonce}".encode("utf-8")
    sig = hmac.new(settings.CSRF_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"{user_id}:{nonce}:{sig}"


def verify_csrf_token(csrf_token: Optional[str], user_id: int) -> bool:
    if not csrf_token:
        return False
    parts = csrf_token.split(":")
    if len(parts) != 3:
        return False
    uid_str, nonce, provided_sig = parts
    if uid_str != str(user_id):
        return False
    msg = f"{uid_str}:{nonce}".encode("utf-8")
    expected_sig = hmac.new(settings.CSRF_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided_sig, expected_sig)


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def get_role_dashboard_url(role_name: str) -> str:
    if role_name == "admin":
        return "/admin/dashboard"
    if role_name == "doctor":
        return "/doctor/dashboard"
    return "/patient/dashboard"


def log_audit_event(
    db: Session,
    action: str,
    resource_type: str,
    actor: Optional[User] = None,
    resource_id: Optional[ Any ] = None,
    patient_id: Optional[int] = None,
    request: Optional[Request] = None,
    details: Optional[Dict[str, Any]] = None,
    actor_email_override: Optional[str] = None,
) -> AuditLog:
    ip_addr = None
    user_agent = None
    if request is not None:
        ip_addr = request.client.host if request.client else None
        user_agent = (request.headers.get("user-agent") or "")[:250]

    safe_details = None
    if details:
        # Ensure sensitive keys are never persisted in audit logs
        scrubbed = {
            k: v
            for k, v in details.items()
            if k.lower() not in {"password", "password_hash", "confirm_password", "token", "secret"}
        }
        safe_details = json.dumps(scrubbed, default=str)

    entry = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_email=actor.email if actor else actor_email_override,
        actor_role=actor.role.name if (actor and actor.role) else None,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        patient_id=patient_id,
        ip_address=ip_addr,
        user_agent=user_agent,
        details_json=safe_details,
    )
    db.add(entry)
    db.flush()
    return entry
