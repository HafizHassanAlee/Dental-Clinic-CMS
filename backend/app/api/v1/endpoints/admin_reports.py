from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.permissions import ROLE_ADMIN
from app.core.security import hash_password, log_audit_event, validate_password_strength
from app.db.session import get_db
from app.dependencies.auth import require_roles
from app.models.entities import (
    Appointment,
    AuditLog,
    ClinicSetting,
    DoctorProfile,
    Invoice,
    PatientProfile,
    Payment,
    RecordCorrectionRequest,
    Review,
    Role,
    Service,
    StaffProfile,
    User,
)
from app.schemas.domain import AdminCreateStaffRequest, ClinicSettingsUpdateRequest


admin_router = APIRouter()
reports_router = APIRouter()


@admin_router.get("/dashboard")
def get_admin_dashboard_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    today = date.today()
    month_start = today.replace(day=1)

    total_patients = db.query(PatientProfile).filter(PatientProfile.is_archived.is_(False)).count()
    new_patients_month = (
        db.query(PatientProfile)
        .filter(func.date(PatientProfile.created_at) >= month_start)
        .count()
    )
    appointments_today = (
        db.query(Appointment).filter(Appointment.appointment_date == today).count()
    )
    upcoming_appointments = (
        db.query(Appointment)
        .filter(
            Appointment.appointment_date > today,
            Appointment.status.in_(["Requested", "Confirmed"]),
        )
        .count()
    )
    completed_appointments = (
        db.query(Appointment).filter(Appointment.status == "Completed").count()
    )
    cancelled_appointments = (
        db.query(Appointment).filter(Appointment.status == "Cancelled").count()
    )

    invoices = (
        db.query(Invoice)
        .filter(Invoice.document_kind == "Invoice", Invoice.status != "Voided")
        .all()
    )
    outstanding_invoices_count = sum(1 for inv in invoices if inv.balance_due > Decimal("0.00"))
    outstanding_balance_total = sum((inv.balance_due for inv in invoices), Decimal("0.00"))

    # Financial metrics strictly based on actual Recorded Payments (never unpaid invoices)
    recorded_payments = (
        db.query(Payment).filter(Payment.status == "Recorded").all()
    )
    total_recorded_revenue = sum((p.amount for p in recorded_payments), Decimal("0.00"))
    monthly_revenue = sum(
        (p.amount for p in recorded_payments if p.payment_date.date() >= month_start),
        Decimal("0.00"),
    )

    pending_reviews = db.query(Review).filter(Review.status == "Pending").count()
    pending_corrections = (
        db.query(RecordCorrectionRequest)
        .filter(RecordCorrectionRequest.status == "Pending")
        .count()
    )

    return {
        "currency": "PKR",
        "metrics": {
            "total_registered_patients": total_patients,
            "new_patient_registrations_this_month": new_patients_month,
            "appointments_today": appointments_today,
            "upcoming_appointments": upcoming_appointments,
            "completed_appointments": completed_appointments,
            "cancelled_appointments": cancelled_appointments,
            "outstanding_invoices_count": outstanding_invoices_count,
            "outstanding_balance_pkr": float(outstanding_balance_total),
            "recorded_payments_count": len(recorded_payments),
            "total_recorded_revenue_pkr": float(total_recorded_revenue),
            "monthly_recorded_revenue_pkr": float(monthly_revenue),
            "pending_reviews_count": pending_reviews,
            "pending_correction_requests_count": pending_corrections,
        },
    }


@admin_router.get("/users")
def list_all_users(
    role: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    query = db.query(User)
    if role:
        query = query.join(Role).filter(Role.name == role)
    users = query.order_by(User.id.asc()).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "phone": u.phone,
            "full_name": u.full_name,
            "role": u.role.name if u.role else "",
            "is_active": u.is_active,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@admin_router.patch("/users/{user_id}/status")
def toggle_user_active_status(
    user_id: int,
    is_active: bool = Query(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.id == current_user.id and not is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own active administrator account.",
        )

    user.is_active = is_active
    if not is_active:
        # Immediately invalidate active tokens for deactivated accounts
        user.token_version += 1

    if user.patient_profile:
        user.patient_profile.is_active = is_active
    if user.doctor_profile:
        user.doctor_profile.is_active = is_active
    if user.staff_profile:
        user.staff_profile.is_active = is_active

    log_audit_event(
        db=db,
        action="USER_ACCOUNT_ACTIVATED" if is_active else "USER_ACCOUNT_DEACTIVATED",
        resource_type="user",
        actor=current_user,
        resource_id=user.id,
        request=request,
        details={"target_email": user.email, "is_active": is_active},
    )
    db.commit()
    return {"id": user.id, "email": user.email, "is_active": user.is_active}


@admin_router.get("/staff")
def list_staff_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    staff_rows = db.query(StaffProfile).order_by(StaffProfile.id.asc()).all()
    return [
        {
            "id": s.id,
            "user_id": s.user_id,
            "staff_code": s.staff_code,
            "full_name": s.full_name,
            "email": s.user.email if s.user else None,
            "phone": s.user.phone if s.user else None,
            "designation": s.designation,
            "department": s.department,
            "can_view_clinical_details": s.can_view_clinical_details,
            "is_active": s.is_active,
        }
        for s in staff_rows
    ]


@admin_router.post("/staff", status_code=status.HTTP_201_CREATED)
def create_staff_account(
    payload: AdminCreateStaffRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    err = validate_password_strength(payload.password)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    email_norm = payload.email.strip().lower()
    if db.query(User).filter(User.email == email_norm).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")

    admin_role = db.query(Role).filter(Role.name == ROLE_ADMIN).first()
    user = User(
        email=email_norm,
        phone=payload.phone.strip(),
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role_id=admin_role.id,
        is_active=True,
        is_email_verified=True,
    )
    db.add(user)
    db.flush()

    next_seq = db.query(StaffProfile).count() + 1
    code = f"STF-{next_seq:04d}"
    staff = StaffProfile(
        user_id=user.id,
        staff_code=code,
        full_name=user.full_name,
        designation=payload.designation,
        department=payload.department,
        can_view_clinical_details=payload.can_view_clinical_details,
        is_active=True,
    )
    db.add(staff)
    log_audit_event(
        db=db,
        action="ADMIN_CREATED_STAFF",
        resource_type="staff_profile",
        actor=current_user,
        resource_id=user.id,
        request=request,
        details={"staff_code": code, "can_view_clinical_details": payload.can_view_clinical_details},
    )
    db.commit()
    db.refresh(staff)
    return {
        "id": staff.id,
        "user_id": staff.user_id,
        "staff_code": staff.staff_code,
        "full_name": staff.full_name,
        "email": user.email,
        "designation": staff.designation,
        "can_view_clinical_details": staff.can_view_clinical_details,
    }


@admin_router.get("/settings")
def get_clinic_settings(db: Session = Depends(get_db)):
    s = db.query(ClinicSetting).first()
    if not s:
        s = ClinicSetting()
        db.add(s)
        db.commit()
        db.refresh(s)
    return {
        "clinic_name": s.clinic_name,
        "tagline": s.tagline,
        "hero_subtitle": s.hero_subtitle,
        "lead_dentist_name": s.lead_dentist_name,
        "about_summary": s.about_summary,
        "phone_primary": s.phone_primary,
        "whatsapp_number": s.whatsapp_number,
        "email_contact": s.email_contact,
        "address_line": s.address_line,
        "city": s.city,
        "country": s.country,
        "google_maps_url": s.google_maps_url,
        "facebook_url": s.facebook_url,
        "opening_hours_days": s.opening_hours_days,
        "opening_hours_time": s.opening_hours_time,
        "opening_time_24h": s.opening_time_24h,
        "closing_time_24h": s.closing_time_24h,
        "currency": s.currency,
        "appointment_slot_minutes": s.appointment_slot_minutes,
        "cancellation_notice_hours": s.cancellation_notice_hours,
    }


@admin_router.put("/settings")
def update_clinic_settings(
    payload: ClinicSettingsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    s = db.query(ClinicSetting).first()
    if not s:
        s = ClinicSetting()
        db.add(s)
        db.flush()

    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        if v is not None:
            setattr(s, k, v)

    log_audit_event(
        db=db,
        action="CLINIC_SETTINGS_UPDATED",
        resource_type="clinic_settings",
        actor=current_user,
        resource_id=s.id,
        request=request,
        details=updates,
    )
    db.commit()
    return get_clinic_settings(db)


@admin_router.get("/audit-logs")
def list_audit_logs(
    action: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action.strip()}%"))
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "actor_user_id": l.actor_user_id,
            "actor_email": l.actor_email,
            "actor_role": l.actor_role,
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "patient_id": l.patient_id,
            "ip_address": l.ip_address,
            "details_json": l.details_json,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


# ============================================================================
# REPORTS ROUTER (/api/v1/reports)
# ============================================================================


@reports_router.get("/summary")
def get_operational_and_financial_reports(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """
    Database-backed operational and financial summary report.
    Never exposes confidential patient medical notes; bases revenue strictly on Recorded payments.
    """
    apts_query = db.query(Appointment)
    if date_from:
        apts_query = apts_query.filter(Appointment.appointment_date >= date_from)
    if date_to:
        apts_query = apts_query.filter(Appointment.appointment_date <= date_to)
    apts = apts_query.all()

    status_breakdown: dict[str, int] = {}
    for a in apts:
        status_breakdown[a.status] = status_breakdown.get(a.status, 0) + 1

    # Service utilization
    service_counts: dict[str, int] = {}
    for a in apts:
        s_name = a.service.name if a.service else "General Consultation"
        service_counts[s_name] = service_counts.get(s_name, 0) + 1

    # Payments summary
    payments = db.query(Payment).filter(Payment.status == "Recorded").all()
    if date_from:
        payments = [p for p in payments if p.payment_date.date() >= date_from]
    if date_to:
        payments = [p for p in payments if p.payment_date.date() <= date_to]

    recorded_revenue = sum((p.amount for p in payments), Decimal("0.00"))
    by_method: dict[str, float] = {}
    for p in payments:
        by_method[p.payment_method] = by_method.get(p.payment_method, 0.0) + float(p.amount)

    invoices = db.query(Invoice).filter(Invoice.document_kind == "Invoice", Invoice.status != "Voided").all()
    total_invoiced = sum((i.total_amount for i in invoices), Decimal("0.00"))
    total_outstanding = sum((i.balance_due for i in invoices), Decimal("0.00"))

    reviews = db.query(Review).all()
    approved_reviews = [r for r in reviews if r.status == "Approved"]
    avg_rating = (
        round(sum(r.rating for r in approved_reviews) / len(approved_reviews), 2)
        if approved_reviews
        else 5.0
    )

    return {
        "currency": "PKR",
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "appointment_summary": {
            "total": len(apts),
            "by_status": status_breakdown,
        },
        "service_utilization": service_counts,
        "financial_summary": {
            "recorded_payments_count": len(payments),
            "recorded_revenue_pkr": float(recorded_revenue),
            "revenue_by_payment_method_pkr": by_method,
            "total_invoiced_pkr": float(total_invoiced),
            "total_outstanding_balance_pkr": float(total_outstanding),
        },
        "review_summary": {
            "total_reviews": len(reviews),
            "approved_reviews": len(approved_reviews),
            "pending_reviews": sum(1 for r in reviews if r.status == "Pending"),
            "average_approved_rating": avg_rating,
        },
    }
