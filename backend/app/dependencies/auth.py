"""FastAPI dependencies for authentication, RBAC, and strict patient data isolation."""
from typing import Callable, Optional
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.permissions import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import (
    COOKIE_ACCESS_TOKEN,
    COOKIE_CSRF_TOKEN,
    HEADER_CSRF_TOKEN,
    decode_access_token,
    log_audit_event,
    verify_csrf_token,
)
from app.db.session import get_db
from app.models.entities import DoctorProfile, PatientProfile, User


SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _extract_token(request: Request) -> tuple[Optional[str], bool]:
    """Return (token, from_cookie)."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip(), False
    cookie_token = request.cookies.get(COOKIE_ACCESS_TOKEN)
    if cookie_token:
        return cookie_token, True
    return None, False


def get_optional_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    token, from_cookie = _extract_token(request)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    try:
        user_id = int(payload.get("sub", 0))
    except (TypeError, ValueError):
        return None

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        return None

    # Verify token_version so password changes or revocations immediately invalidate old sessions
    if payload.get("ver") != user.token_version:
        return None

    # Enforce CSRF verification on mutating cookie-authenticated requests
    if from_cookie and request.method.upper() not in SAFE_METHODS:
        csrf_header = request.headers.get(HEADER_CSRF_TOKEN)
        csrf_cookie = request.cookies.get(COOKIE_CSRF_TOKEN)
        token_to_verify = csrf_header or csrf_cookie
        if not verify_csrf_token(token_to_verify, user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed. Please refresh and try again.",
            )

    return user


def get_current_user(
    user: Optional[User] = Depends(get_optional_current_user),
) -> User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in to continue.",
        )
    return user


def require_roles(*allowed_roles: str) -> Callable:
    def _dep(user: User = Depends(get_current_user)) -> User:
        role_name = user.role.name if user.role else ""
        if role_name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: This endpoint requires one of roles {list(allowed_roles)}.",
            )
        return user

    return _dep


def get_current_patient_profile(
    user: User = Depends(require_roles(ROLE_PATIENT)),
    db: Session = Depends(get_db),
) -> PatientProfile:
    """Strictly resolves the PatientProfile from the server-side authenticated User account."""
    profile = db.query(PatientProfile).filter(PatientProfile.user_id == user.id).first()
    if not profile or not profile.is_active or profile.is_archived:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active patient profile not found for this account.",
        )
    return profile


def get_current_doctor_profile(
    user: User = Depends(require_roles(ROLE_DOCTOR)),
    db: Session = Depends(get_db),
) -> DoctorProfile:
    """Strictly resolves the DoctorProfile from the server-side authenticated User account."""
    profile = db.query(DoctorProfile).filter(DoctorProfile.user_id == user.id).first()
    if not profile or not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active doctor profile not found for this account.",
        )
    return profile


def get_current_admin(
    user: User = Depends(require_roles(ROLE_ADMIN)),
) -> User:
    return user


def verify_patient_isolation(
    db: Session,
    current_user: User,
    target_patient_id: int,
    request: Optional[Request] = None,
    resource_label: str = "patient_record",
) -> PatientProfile:
    """
    Mandatory patient data isolation guard:
    - If the user is a Patient, their authenticated PatientProfile.id MUST match target_patient_id.
      Any mismatch logs a security event and raises HTTP 403 without leaking record contents.
    - If the user is a Doctor or Admin, verifies the patient exists and logs sensitive access.
    """
    role_name = current_user.role.name if current_user.role else ""
    if role_name == ROLE_PATIENT:
        own_profile = db.query(PatientProfile).filter(PatientProfile.user_id == current_user.id).first()
        if not own_profile or own_profile.id != target_patient_id:
            log_audit_event(
                db=db,
                action="UNAUTHORIZED_PATIENT_ACCESS_ATTEMPT",
                resource_type=resource_label,
                actor=current_user,
                resource_id=target_patient_id,
                patient_id=target_patient_id,
                request=request,
                details={"attempted_patient_id": target_patient_id},
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are strictly only authorized to access your own patient records.",
            )
        return own_profile

    if role_name in (ROLE_DOCTOR, ROLE_ADMIN):
        patient = db.query(PatientProfile).filter(PatientProfile.id == target_patient_id).first()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requested patient record was not found.",
            )
        if role_name == ROLE_ADMIN and current_user.staff_profile:
            if not current_user.staff_profile.can_view_clinical_details and resource_label in {
                "clinical_encounter",
                "dental_chart",
                "prescription",
                "clinical_document",
            }:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Administrative account lacks explicit clinical record viewing permission.",
                )
        return patient

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions to access patient data.",
    )
