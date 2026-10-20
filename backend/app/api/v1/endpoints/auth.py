from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.permissions import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import (
    COOKIE_ACCESS_TOKEN,
    COOKIE_CSRF_TOKEN,
    create_access_token,
    generate_csrf_token,
    generate_reset_token,
    get_role_dashboard_url,
    hash_password,
    hash_reset_token,
    log_audit_event,
    validate_password_strength,
    verify_password,
)
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.entities import (
    ConsentRecord,
    DoctorProfile,
    MedicalHistory,
    PasswordResetToken,
    PatientProfile,
    Role,
    User,
)
from app.schemas.domain import (
    AuthTokenResponse,
    ForgotPasswordRequest,
    LoginRequest,
    PasswordChangeRequest,
    PatientRegisterRequest,
    ResetPasswordRequest,
    SendOtpRequest,
    UserSummaryOut,
    VerifyOtpRequest,
)
from app.services.notification_service import create_user_notification
from app.services.seed_service import ensure_roles_and_permissions
from app.services.verification_service import (
    generate_and_send_verification_otp,
    verify_user_otp_code,
)


router = APIRouter()


def _set_auth_cookies(response: Response, access_token: str, csrf_token: str) -> None:
    max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key=COOKIE_ACCESS_TOKEN,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        key=COOKIE_CSRF_TOKEN,
        value=csrf_token,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def _generate_next_patient_number(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"RDC-{year}-"
    last_patient = (
        db.query(PatientProfile)
        .filter(PatientProfile.patient_number.like(f"{prefix}%"))
        .order_by(PatientProfile.id.desc())
        .first()
    )
    next_seq = 1
    if last_patient and last_patient.patient_number.startswith(prefix):
        try:
            next_seq = int(last_patient.patient_number.split("-")[-1]) + 1
        except ValueError:
            next_seq = db.query(PatientProfile).count() + 1
    else:
        next_seq = db.query(PatientProfile).count() + 1
    return f"{prefix}{next_seq:05d}"


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register_patient(
    payload: PatientRegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Public self-registration strictly creates a Patient account.
    Patients can never select a doctor or administrator role during registration.
    """
    if payload.password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password and confirmation password do not match.",
        )

    pwd_err = validate_password_strength(payload.password)
    if pwd_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pwd_err)

    email_norm = payload.email.strip().lower()
    existing_user = db.query(User).filter(User.email == email_norm).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address is already registered.",
        )

    roles = ensure_roles_and_permissions(db)
    patient_role = roles[ROLE_PATIENT]

    user = User(
        email=email_norm,
        phone=payload.phone.strip(),
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role_id=patient_role.id,
        is_active=True,
        is_email_verified=False,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()

    default_doctor = db.query(DoctorProfile).filter(DoctorProfile.is_active.is_(True)).first()
    patient_number = _generate_next_patient_number(db)

    profile = PatientProfile(
        user_id=user.id,
        patient_number=patient_number,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone or payload.phone.strip(),
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        address=payload.address,
        city="Lahore",
        primary_doctor_id=default_doctor.id if default_doctor else None,
        is_active=True,
    )
    db.add(profile)
    db.flush()

    db.add(
        MedicalHistory(
            patient_id=profile.id,
            systemic_conditions="None reported at registration",
            updated_by_id=user.id,
        )
    )
    db.add(
        ConsentRecord(
            patient_id=profile.id,
            user_id=user.id,
            consent_type="PrivacyPolicyAndTerms",
            consent_version="v1.0",
            is_accepted=True,
            ip_address=request.client.host if request.client else None,
            notes="Accepted during public patient registration",
        )
    )

    create_user_notification(
        db=db,
        user_id=user.id,
        title="Welcome to Rumi Dental Care",
        message=f"Your patient portal account ({patient_number}) is ready. You can now book appointments and view your dental records.",
        notification_type="System",
    )

    log_audit_event(
        db=db,
        action="PATIENT_REGISTERED",
        resource_type="user",
        actor=user,
        resource_id=user.id,
        patient_id=profile.id,
        request=request,
        details={"patient_number": patient_number, "verification_channel": payload.verification_channel},
    )
    db.commit()
    db.refresh(user)

    verification_info = generate_and_send_verification_otp(
        db=db,
        user=user,
        channel=payload.verification_channel or "email",
        client_ip=request.client.host if request.client else None,
    )

    access_token = create_access_token(user.id, ROLE_PATIENT, user.token_version)
    csrf_token = generate_csrf_token(user.id)
    _set_auth_cookies(response, access_token, csrf_token)
    redirect_url = get_role_dashboard_url(ROLE_PATIENT)

    return AuthTokenResponse(
        access_token=access_token,
        csrf_token=csrf_token,
        role=ROLE_PATIENT,
        redirect_url=redirect_url,
        user=UserSummaryOut(
            id=user.id,
            email=user.email,
            phone=user.phone,
            full_name=user.full_name,
            role_name=ROLE_PATIENT,
            is_active=user.is_active,
            is_email_verified=user.is_email_verified,
            redirect_url=redirect_url,
        ),
        verification_info=verification_info,
    )


def _perform_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session,
    allowed_roles: set[str],
    portal_label: str,
) -> AuthTokenResponse:
    now = datetime.now(timezone.utc)
    email_norm = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_norm).first()

    if not user:
        log_audit_event(
            db=db,
            action="LOGIN_FAILED_UNKNOWN_EMAIL",
            resource_type="auth",
            request=request,
            actor_email_override=email_norm,
            details={"portal": portal_label},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email address or password.",
        )

    if not user.is_active:
        log_audit_event(
            db=db,
            action="LOGIN_FAILED_DEACTIVATED_ACCOUNT",
            resource_type="auth",
            actor=user,
            resource_id=user.id,
            request=request,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Please contact Rumi Dental Care administration.",
        )

    if user.locked_until and user.locked_until > now:
        remaining_min = max(1, int((user.locked_until - now).total_seconds() // 60))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account is temporarily locked due to multiple failed login attempts. Try again in {remaining_min} minute(s).",
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= settings.LOGIN_MAX_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
        log_audit_event(
            db=db,
            action="LOGIN_FAILED_BAD_PASSWORD",
            resource_type="auth",
            actor=user,
            resource_id=user.id,
            request=request,
            details={"attempts": user.failed_login_attempts, "portal": portal_label},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email address or password.",
        )

    role_name = user.role.name if user.role else ""
    if role_name not in allowed_roles:
        log_audit_event(
            db=db,
            action="LOGIN_REJECTED_WRONG_PORTAL",
            resource_type="auth",
            actor=user,
            resource_id=user.id,
            request=request,
            details={"user_role": role_name, "attempted_portal": portal_label},
        )
        db.commit()
        if portal_label == "patient_portal":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff and doctor accounts must sign in via the dedicated Staff Login page (/staff/login).",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patient accounts must sign in via the Patient Login page (/login).",
        )

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now

    log_audit_event(
        db=db,
        action="LOGIN_SUCCESS",
        resource_type="auth",
        actor=user,
        resource_id=user.id,
        request=request,
        details={"portal": portal_label, "role": role_name},
    )
    db.commit()

    access_token = create_access_token(user.id, role_name, user.token_version)
    csrf_token = generate_csrf_token(user.id)
    _set_auth_cookies(response, access_token, csrf_token)
    redirect_url = get_role_dashboard_url(role_name)

    return AuthTokenResponse(
        access_token=access_token,
        csrf_token=csrf_token,
        role=role_name,
        redirect_url=redirect_url,
        user=UserSummaryOut(
            id=user.id,
            email=user.email,
            phone=user.phone,
            full_name=user.full_name,
            role_name=role_name,
            is_active=user.is_active,
            is_email_verified=user.is_email_verified,
            redirect_url=redirect_url,
        ),
    )


@router.post("/patient/login", response_model=AuthTokenResponse)
@router.post("/login", response_model=AuthTokenResponse)
def patient_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Public patient login endpoint. Rejects doctor/admin accounts."""
    return _perform_login(
        payload=payload,
        request=request,
        response=response,
        db=db,
        allowed_roles={ROLE_PATIENT},
        portal_label="patient_portal",
    )


@router.post("/staff/login", response_model=AuthTokenResponse)
def staff_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Dedicated staff login endpoint for Doctors and Administrators only."""
    return _perform_login(
        payload=payload,
        request=request,
        response=response,
        db=db,
        allowed_roles={ROLE_DOCTOR, ROLE_ADMIN},
        portal_label="staff_portal",
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    log_audit_event(
        db=db,
        action="LOGOUT",
        resource_type="auth",
        actor=current_user,
        resource_id=current_user.id,
        request=request,
    )
    db.commit()
    response.delete_cookie(COOKIE_ACCESS_TOKEN, path="/")
    response.delete_cookie(COOKIE_CSRF_TOKEN, path="/")
    return {"message": "Successfully logged out."}


@router.get("/me", response_model=UserSummaryOut)
def get_me(current_user: User = Depends(get_current_user)):
    role_name = current_user.role.name if current_user.role else ROLE_PATIENT
    return UserSummaryOut(
        id=current_user.id,
        email=current_user.email,
        phone=current_user.phone,
        full_name=current_user.full_name,
        role_name=role_name,
        is_active=current_user.is_active,
        is_email_verified=current_user.is_email_verified,
        redirect_url=get_role_dashboard_url(role_name),
    )


@router.post("/change-password")
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation do not match.",
        )
    err = validate_password_strength(payload.new_password)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    current_user.password_hash = hash_password(payload.new_password)
    current_user.token_version += 1
    log_audit_event(
        db=db,
        action="PASSWORD_CHANGED",
        resource_type="user",
        actor=current_user,
        resource_id=current_user.id,
        request=request,
    )
    db.commit()

    role_name = current_user.role.name if current_user.role else ROLE_PATIENT
    new_token = create_access_token(current_user.id, role_name, current_user.token_version)
    new_csrf = generate_csrf_token(current_user.id)
    _set_auth_cookies(response, new_token, new_csrf)
    return {"message": "Password updated successfully.", "csrf_token": new_csrf}


@router.post("/forgot-password")
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Generates a short-lived, single-use password reset token without revealing whether the email exists.
    In development/test mode (when SMTP is not configured), returns `dev_reset_token` only in non-production
    so automated tests and local developers can exercise the reset workflow end-to-end.
    """
    email_norm = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_norm, User.is_active.is_(True)).first()
    dev_token = None

    if user:
        raw_token = generate_reset_token()
        token_hash = hash_reset_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
                requested_ip=request.client.host if request.client else None,
            )
        )
        log_audit_event(
            db=db,
            action="PASSWORD_RESET_REQUESTED",
            resource_type="user",
            actor=user,
            resource_id=user.id,
            request=request,
        )
        db.commit()
        if settings.APP_ENV.lower() in {"development", "test", "local"}:
            dev_token = raw_token

    result = {
        "message": "If an active account with that email exists, password reset instructions have been issued."
    }
    if dev_token and settings.APP_ENV.lower() in {"development", "test", "local"}:
        result["dev_reset_token"] = dev_token
    return result


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation password do not match.",
        )
    err = validate_password_strength(payload.new_password)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    now = datetime.now(timezone.utc)
    token_hash = hash_reset_token(payload.token.strip())
    reset_record = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )

    if not reset_record or reset_record.used_at is not None or reset_record.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already used password reset token.",
        )

    user = db.query(User).filter(User.id == reset_record.user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset request.")

    reset_record.used_at = now
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1
    user.failed_login_attempts = 0
    user.locked_until = None

    log_audit_event(
        db=db,
        action="PASSWORD_RESET_COMPLETED",
        resource_type="user",
        actor=user,
        resource_id=user.id,
        request=request,
    )
    db.commit()
    return {"message": "Password has been reset successfully. You may now sign in."}


@router.post("/send-verification-otp")
def send_verification_otp(
    payload: SendOtpRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sends a 6-digit account verification code to the authenticated user via:
    - 'email': from muhammadhafizhassan228@gmail.com to the patient's email
    - 'whatsapp' / 'phone': via WhatsApp / SMS link to the patient's phone number
    """
    info = generate_and_send_verification_otp(
        db=db,
        user=current_user,
        channel=payload.channel,
        client_ip=request.client.host if request.client else None,
    )
    log_audit_event(
        db=db,
        action="ACCOUNT_VERIFICATION_OTP_SENT",
        resource_type="user",
        actor=current_user,
        resource_id=current_user.id,
        request=request,
        details={"channel": info["channel"], "sender": info["sender"]},
    )
    db.commit()
    return info


@router.post("/verify-otp")
def verify_account_otp(
    payload: VerifyOtpRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verifies the 6-digit OTP code sent via email (muhammadhafizhassan228@gmail.com) or WhatsApp/Phone
    and marks the patient account as verified.
    """
    ok = verify_user_otp_code(db, current_user, payload.otp_code)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code. Please check your 6-digit code or request a new one.",
        )

    create_user_notification(
        db=db,
        user_id=current_user.id,
        title="Account Verified Successfully",
        message="Your email/phone verification is complete. Thank you for verifying your Rumi Dental Care account.",
        notification_type="System",
    )
    log_audit_event(
        db=db,
        action="ACCOUNT_VERIFIED_OTP",
        resource_type="user",
        actor=current_user,
        resource_id=current_user.id,
        request=request,
    )
    db.commit()
    return {
        "verified": True,
        "message": "Your account has been verified successfully!",
        "redirect_url": get_role_dashboard_url(current_user.role.name if current_user.role else ROLE_PATIENT),
    }
