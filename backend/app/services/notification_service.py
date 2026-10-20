from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.entities import Notification


def create_user_notification(
    db: Session,
    user_id: Optional[int],
    title: str,
    message: str,
    notification_type: str = "System",
    related_entity_type: Optional[str] = None,
    related_entity_id: Optional[int] = None,
) -> Optional[Notification]:
    """
    Create an in-app notification for a user.
    If SMTP/SMS credentials are not configured in .env, records honest delivery status
    'InAppDelivered (External Provider Not Configured)' without pretending external messages were sent.
    """
    if not user_id:
        return None

    ext_status = "InAppDelivered"
    if settings.SMTP_HOST and settings.SMTP_USER:
        ext_status = "InAppDelivered_SMTPConfigured"

    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        is_read=False,
        channel="InApp",
        external_delivery_status=ext_status,
    )
    db.add(notif)
    db.flush()
    return notif
