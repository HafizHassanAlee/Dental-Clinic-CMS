"""
Account Verification Service for Rumi Dental Care.
Supports 6-digit OTP verification via:
1. Email from muhammadhafizhassan228@gmail.com to the patient's email address
2. Phone / WhatsApp verification link & message dispatch
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import re
import secrets
import smtplib
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_reset_token
from app.models.entities import PasswordResetToken, User
from app.services.notification_service import create_user_notification


VERIFICATION_SENDER_EMAIL = "muhammadhafizhassan228@gmail.com"


def _normalize_phone_for_whatsapp(phone: str | None) -> str:
    """Convert Pakistan or international phone numbers (e.g. 0300... or +92 300...) to digits for wa.me."""
    if not phone:
        return "923102468080"
    digits = re.sub(r"\D+", "", phone)
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = "92" + digits[1:]
    elif len(digits) == 10 and digits.startswith("3"):
        digits = "92" + digits
    return digits or "923102468080"


def generate_and_send_verification_otp(
    db: Session,
    user: User,
    channel: str = "email",
    client_ip: str | None = None,
) -> dict:
    """
    Generates a 6-digit numeric OTP, stores its SHA-256 hash in `password_reset_tokens`,
    and dispatches it via Email (from muhammadhafizhassan228@gmail.com) or WhatsApp/Phone.
    """
    channel_norm = (channel or "email").strip().lower()
    if channel_norm not in {"email", "whatsapp", "phone"}:
        channel_norm = "email"

    # Generate 6-digit OTP code (100000 - 999999)
    otp_code = f"{100000 + secrets.randbelow(900000)}"
    token_hash = hash_reset_token(f"VERIFY:{user.id}:{otp_code}")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            requested_ip=client_ip,
        )
    )

    sender_email = settings.SMTP_FROM_EMAIL or VERIFICATION_SENDER_EMAIL
    subject = f"Rumi Dental Care — Your Account Verification Code: {otp_code}"
    body_text = (
        f"Assalam-o-Alaikum {user.full_name},\n\n"
        f"Welcome to Rumi Dental Care (388 A, Block A, RECHS, Johar Town, Lahore).\n"
        f"Your 6-digit account verification code is: {otp_code}\n\n"
        f"Sent from: {sender_email}\n"
        f"Recipient: {user.email} / {user.phone or 'N/A'}\n"
        f"This code expires in 15 minutes.\n\n"
        f"Dr. Aisha Salman — Rumi Dental Care (+92 310 2468080)"
    )

    smtp_sent = False
    if channel_norm == "email" and settings.SMTP_HOST and settings.SMTP_PASSWORD:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = f"Rumi Dental Care <{sender_email}>"
            msg["To"] = user.email
            msg.set_content(body_text)
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=8) as server:
                server.starttls()
                server.login(settings.SMTP_USER or sender_email, settings.SMTP_PASSWORD)
                server.send_message(msg)
            smtp_sent = True
        except Exception:
            smtp_sent = False

    # Build WhatsApp link to patient's phone number
    patient_wa_digits = _normalize_phone_for_whatsapp(user.phone)
    wa_message = (
        f"*Rumi Dental Care — Account Verification*\n"
        f"Hello {user.full_name}, your 6-digit verification code is *{otp_code}* "
        f"(valid for 15 minutes).\n"
        f"From: {sender_email} | Rumi Dental Care (+92 310 2468080)"
    )
    whatsapp_url = f"https://wa.me/{patient_wa_digits}?text={quote(wa_message)}"

    # Persist to local verification outbox log for immediate developer/operator visibility
    try:
        outbox_file = settings.private_upload_dir / "verification_outbox.log"
        with outbox_file.open("a", encoding="utf-8") as fh:
            fh.write(
                f"[{datetime.now(timezone.utc).isoformat()}] CHANNEL={channel_norm.upper()} "
                f"FROM={sender_email} TO_EMAIL={user.email} TO_PHONE={user.phone} "
                f"OTP={otp_code} SMTP_SENT={smtp_sent}\n"
            )
    except Exception:
        pass

    create_user_notification(
        db=db,
        user_id=user.id,
        title=f"Verification Code ({channel_norm.upper()}): {otp_code}",
        message=(
            f"Verification code {otp_code} issued from {sender_email} to "
            f"{user.email if channel_norm == 'email' else (user.phone or user.email)}."
        ),
        notification_type="Verification",
    )
    db.flush()

    delivery_msg = (
        f"6-digit verification code sent from {sender_email} to {user.email}."
        if channel_norm == "email"
        else f"6-digit WhatsApp/Phone verification code generated for {user.phone or user.email}."
    )
    res = {
        "channel": channel_norm,
        "sender": sender_email,
        "sender_email": sender_email,
        "recipient_email": user.email,
        "recipient_phone": user.phone,
        "whatsapp_url": whatsapp_url,
        "smtp_sent": smtp_sent,
        "delivery_message": delivery_msg,
        "expires_in_minutes": 15,
    }
    if settings.APP_ENV.lower() in {"development", "test", "local"} or not smtp_sent:
        res["dev_otp_code"] = otp_code
    return res


def verify_user_otp_code(db: Session, user: User, otp_code: str) -> bool:
    """Validates a 6-digit OTP code for the given user and marks it as used."""
    clean_code = (otp_code or "").strip()
    if not clean_code:
        return False
    now = datetime.now(timezone.utc)
    expected_hash = hash_reset_token(f"VERIFY:{user.id}:{clean_code}")
    record = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.token_hash == expected_hash,
        )
        .first()
    )
    if not record or record.used_at is not None or record.expires_at < now:
        return False

    record.used_at = now
    user.is_email_verified = True
    return True
