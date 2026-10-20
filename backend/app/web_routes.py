from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.permissions import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import COOKIE_CSRF_TOKEN, generate_csrf_token
from app.db.session import get_db
from app.dependencies.auth import get_optional_current_user, verify_patient_isolation
from app.models.entities import (
    Allergy,
    Appointment,
    AuditLog,
    ClinicalDocument,
    ClinicalEncounter,
    ClinicSetting,
    DoctorProfile,
    Invoice,
    MedicalHistory,
    Notification,
    PatientProfile,
    Payment,
    Prescription,
    Receipt,
    RecordCorrectionRequest,
    Review,
    Service,
    StaffProfile,
    TreatmentPlan,
    TreatmentRecord,
    User,
)
from app.services.dental_chart_catalog import get_patient_dental_chart


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

web_router = APIRouter()


def _base_ctx(request: Request, db: Session, user: Optional[User] = None, **extra) -> dict:
    clinic = db.query(ClinicSetting).first() or ClinicSetting()
    notifications = []
    unread_count = 0
    csrf_token = ""
    if user:
        csrf_token = request.cookies.get(COOKIE_CSRF_TOKEN) or generate_csrf_token(user.id)
        notifications = (
            db.query(Notification)
            .filter(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(8)
            .all()
        )
        unread_count = (
            db.query(Notification)
            .filter(Notification.user_id == user.id, Notification.is_read.is_(False))
            .count()
        )
    return {
        "request": request,
        "clinic": clinic,
        "current_user": user,
        "csrf_token": csrf_token,
        "notifications": notifications,
        "unread_notifications_count": unread_count,
        "today_iso": date.today().isoformat(),
        **extra,
    }


def _require_web_role(user: Optional[User], required_role: str, staff_login: bool = False):
    """
    If unauthenticated, redirects to /login (or /staff/login for staff portals).
    If authenticated with a different role, raises HTTP 403 Forbidden to prevent cross-role dashboard access.
    """
    if not user:
        target = "/staff/login" if staff_login else "/login"
        return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)
    actual_role = user.role.name if user.role else ""
    if actual_role != required_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Authenticated '{actual_role}' users cannot access the '{required_role}' dashboard.",
        )
    return None


# ============================================================================
# PUBLIC MARKETING WEBSITE ROUTES
# ============================================================================


@web_router.get("/", response_class=HTMLResponse)
def public_home_page(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    services = (
        db.query(Service)
        .filter(Service.is_published.is_(True))
        .order_by(Service.display_order.asc())
        .all()
    )
    doctors = (
        db.query(DoctorProfile)
        .filter(DoctorProfile.is_active.is_(True), DoctorProfile.is_public.is_(True))
        .all()
    )
    reviews = (
        db.query(Review)
        .filter(
            Review.status == "Approved",
            Review.consent_to_publish.is_(True),
            Review.is_deletion_requested.is_(False),
        )
        .order_by(Review.id.asc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "public/home.html",
        _base_ctx(
            request,
            db,
            user,
            page_title="Home — Rumi Dental Care | Johar Town, Lahore",
            services=services,
            doctors=doctors,
            reviews=reviews,
        ),
    )


@web_router.get("/about", response_class=HTMLResponse)
def public_about_page(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    doctors = (
        db.query(DoctorProfile)
        .filter(DoctorProfile.is_active.is_(True), DoctorProfile.is_public.is_(True))
        .all()
    )
    return templates.TemplateResponse(
        request,
        "public/about.html",
        _base_ctx(request, db, user, page_title="About Us — Rumi Dental Care", doctors=doctors),
    )


@web_router.get("/services", response_class=HTMLResponse)
def public_services_page(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    services = (
        db.query(Service)
        .filter(Service.is_published.is_(True))
        .order_by(Service.display_order.asc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "public/services.html",
        _base_ctx(request, db, user, page_title="Dental Procedures & Services — Rumi Dental Care", services=services),
    )


@web_router.get("/services/{slug}", response_class=HTMLResponse)
def public_service_detail_page(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    service = db.query(Service).filter(Service.slug == slug, Service.is_published.is_(True)).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found.")
    all_services = (
        db.query(Service)
        .filter(Service.is_published.is_(True))
        .order_by(Service.display_order.asc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "public/service_detail.html",
        _base_ctx(
            request,
            db,
            user,
            page_title=f"{service.name} — Rumi Dental Care",
            service=service,
            all_services=all_services,
        ),
    )


@web_router.get("/contact", response_class=HTMLResponse)
@web_router.get("/appointment-info", response_class=HTMLResponse)
@web_router.get("/faq", response_class=HTMLResponse)
@web_router.get("/reviews", response_class=HTMLResponse)
@web_router.get("/privacy-policy", response_class=HTMLResponse)
@web_router.get("/terms-of-service", response_class=HTMLResponse)
@web_router.get("/accessibility", response_class=HTMLResponse)
def public_info_pages(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    path = request.url.path.strip("/")
    reviews = (
        db.query(Review)
        .filter(
            Review.status == "Approved",
            Review.consent_to_publish.is_(True),
            Review.is_deletion_requested.is_(False),
        )
        .order_by(Review.id.asc())
        .all()
    )
    services = (
        db.query(Service)
        .filter(Service.is_published.is_(True))
        .order_by(Service.display_order.asc())
        .all()
    )
    titles = {
        "contact": "Contact & Location — Rumi Dental Care",
        "appointment-info": "Appointment Information — Rumi Dental Care",
        "faq": "Frequently Asked Questions — Rumi Dental Care",
        "reviews": "Patient Reviews & Happy Stories — Rumi Dental Care",
        "privacy-policy": "Privacy Policy & Patient Confidentiality — Rumi Dental Care",
        "terms-of-service": "Terms of Service — Rumi Dental Care",
        "accessibility": "Accessibility Statement — Rumi Dental Care",
    }
    return templates.TemplateResponse(
        request,
        "public/info_pages.html",
        _base_ctx(
            request,
            db,
            user,
            page_key=path,
            page_title=titles.get(path, "Rumi Dental Care"),
            reviews=reviews,
            services=services,
        ),
    )


# ============================================================================
# AUTHENTICATION ENTRY POINTS (/login, /register, /forgot-password, /staff/login)
# ============================================================================


@web_router.get("/login", response_class=HTMLResponse)
def patient_login_page(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    return templates.TemplateResponse(
        request,
        "auth/patient_login.html",
        _base_ctx(request, db, user, page_title="Patient Portal Login — Rumi Dental Care"),
    )


@web_router.get("/register", response_class=HTMLResponse)
def patient_register_page(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    return templates.TemplateResponse(
        request,
        "auth/patient_register.html",
        _base_ctx(request, db, user, page_title="Create Patient Account — Rumi Dental Care"),
    )


@web_router.get("/forgot-password", response_class=HTMLResponse)
@web_router.get("/reset-password", response_class=HTMLResponse)
def password_recovery_page(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    mode = "reset" if "reset" in request.url.path else "forgot"
    return templates.TemplateResponse(
        request,
        "auth/password_recovery.html",
        _base_ctx(request, db, user, mode=mode, page_title="Password Recovery — Rumi Dental Care"),
    )


@web_router.get("/staff/login", response_class=HTMLResponse)
def staff_login_page(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    return templates.TemplateResponse(
        request,
        "auth/staff_login.html",
        _base_ctx(request, db, user, page_title="Authorized Staff & Doctor Login — Rumi Dental Care"),
    )


# ============================================================================
# PATIENT PORTAL ROUTES (/patient/*)
# ============================================================================


@web_router.get("/patient/dashboard", response_class=HTMLResponse)
@web_router.get("/patient/profile", response_class=HTMLResponse)
@web_router.get("/patient/appointments", response_class=HTMLResponse)
@web_router.get("/patient/medical-history", response_class=HTMLResponse)
@web_router.get("/patient/dental-chart", response_class=HTMLResponse)
@web_router.get("/patient/treatments", response_class=HTMLResponse)
@web_router.get("/patient/x-rays", response_class=HTMLResponse)
@web_router.get("/patient/documents", response_class=HTMLResponse)
@web_router.get("/patient/prescriptions", response_class=HTMLResponse)
@web_router.get("/patient/billing", response_class=HTMLResponse)
@web_router.get("/patient/receipts", response_class=HTMLResponse)
@web_router.get("/patient/reviews", response_class=HTMLResponse)
@web_router.get("/patient/settings", response_class=HTMLResponse)
def patient_portal_pages(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    redir = _require_web_role(user, ROLE_PATIENT, staff_login=False)
    if redir:
        return redir

    section = request.url.path.split("/patient/")[-1].strip("/") or "dashboard"
    patient = db.query(PatientProfile).filter(PatientProfile.user_id == user.id).first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Patient profile not found.")

    appointments = (
        db.query(Appointment)
        .filter(Appointment.patient_id == patient.id)
        .order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc())
        .all()
    )
    encounters = (
        db.query(ClinicalEncounter)
        .filter(ClinicalEncounter.patient_id == patient.id)
        .order_by(ClinicalEncounter.visit_date.desc())
        .all()
    )
    treatments = (
        db.query(TreatmentRecord)
        .filter(TreatmentRecord.patient_id == patient.id)
        .order_by(TreatmentRecord.performed_date.desc())
        .all()
    )
    plans = (
        db.query(TreatmentPlan)
        .filter(TreatmentPlan.patient_id == patient.id)
        .order_by(TreatmentPlan.created_at.desc())
        .all()
    )
    prescriptions = (
        db.query(Prescription)
        .filter(Prescription.patient_id == patient.id)
        .order_by(Prescription.issue_date.desc())
        .all()
    )
    documents = (
        db.query(ClinicalDocument)
        .filter(ClinicalDocument.patient_id == patient.id, ClinicalDocument.is_patient_visible.is_(True))
        .order_by(ClinicalDocument.created_at.desc())
        .all()
    )
    invoices = (
        db.query(Invoice)
        .filter(Invoice.patient_id == patient.id, Invoice.status != "Voided")
        .order_by(Invoice.issue_date.desc())
        .all()
    )
    receipts = (
        db.query(Receipt)
        .filter(Receipt.patient_id == patient.id, Receipt.is_voided.is_(False))
        .order_by(Receipt.issued_at.desc())
        .all()
    )
    my_reviews = (
        db.query(Review)
        .filter(Review.patient_id == patient.id)
        .order_by(Review.created_at.desc())
        .all()
    )
    doctors = db.query(DoctorProfile).filter(DoctorProfile.is_active.is_(True)).all()
    services = (
        db.query(Service)
        .filter(Service.is_published.is_(True), Service.is_bookable.is_(True))
        .order_by(Service.display_order.asc())
        .all()
    )
    dental_chart = get_patient_dental_chart(db, patient.id)
    outstanding_balance = sum(
        (inv.balance_due for inv in invoices if inv.document_kind == "Invoice"), Decimal("0.00")
    )

    return templates.TemplateResponse(
        request,
        "patient/portal.html",
        _base_ctx(
            request,
            db,
            user,
            section=section,
            page_title=f"Patient Portal ({section.replace('-', ' ').title()}) — Rumi Dental Care",
            patient=patient,
            appointments=appointments,
            encounters=encounters,
            treatments=treatments,
            plans=plans,
            prescriptions=prescriptions,
            documents=documents,
            invoices=invoices,
            receipts=receipts,
            my_reviews=my_reviews,
            doctors=doctors,
            services=services,
            dental_chart=dental_chart,
            outstanding_balance=outstanding_balance,
        ),
    )


# ============================================================================
# DOCTOR WORKSPACE ROUTES (/doctor/*)
# ============================================================================


@web_router.get("/doctor/dashboard", response_class=HTMLResponse)
@web_router.get("/doctor/appointments", response_class=HTMLResponse)
@web_router.get("/doctor/patients", response_class=HTMLResponse)
@web_router.get("/doctor/clinical-records", response_class=HTMLResponse)
@web_router.get("/doctor/dental-chart", response_class=HTMLResponse)
@web_router.get("/doctor/treatments", response_class=HTMLResponse)
@web_router.get("/doctor/prescriptions", response_class=HTMLResponse)
@web_router.get("/doctor/documents", response_class=HTMLResponse)
@web_router.get("/doctor/schedule", response_class=HTMLResponse)
@web_router.get("/doctor/profile", response_class=HTMLResponse)
def doctor_workspace_pages(
    request: Request,
    patient_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    redir = _require_web_role(user, ROLE_DOCTOR, staff_login=True)
    if redir:
        return redir

    section = request.url.path.split("/doctor/")[-1].strip("/") or "dashboard"
    doctor = db.query(DoctorProfile).filter(DoctorProfile.user_id == user.id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Doctor profile not found.")

    patients = (
        db.query(PatientProfile)
        .filter(PatientProfile.is_archived.is_(False))
        .order_by(PatientProfile.id.asc())
        .all()
    )
    selected_patient = None
    effective_pid = patient_id
    if not effective_pid:
        cookie_pid = request.cookies.get("rumi_doctor_patient_id")
        if cookie_pid and cookie_pid.isdigit():
            effective_pid = int(cookie_pid)

    if effective_pid:
        selected_patient = (
            db.query(PatientProfile)
            .filter(PatientProfile.id == effective_pid, PatientProfile.is_archived.is_(False))
            .first()
        )
    if not selected_patient and patients:
        selected_patient = patients[0]

    appointments = (
        db.query(Appointment)
        .filter(Appointment.doctor_id == doctor.id)
        .order_by(Appointment.appointment_date.desc(), Appointment.start_time.asc())
        .all()
    )

    enc_query = db.query(ClinicalEncounter).filter(ClinicalEncounter.doctor_id == doctor.id)
    plan_query = db.query(TreatmentPlan).filter(TreatmentPlan.doctor_id == doctor.id)
    tr_query = db.query(TreatmentRecord).filter(TreatmentRecord.doctor_id == doctor.id)
    rx_query = db.query(Prescription).filter(Prescription.doctor_id == doctor.id)
    doc_query = db.query(ClinicalDocument)

    if selected_patient and section in {"clinical-records", "dental-chart", "treatments", "prescriptions", "documents"}:
        enc_query = enc_query.filter(ClinicalEncounter.patient_id == selected_patient.id)
        plan_query = plan_query.filter(TreatmentPlan.patient_id == selected_patient.id)
        tr_query = tr_query.filter(TreatmentRecord.patient_id == selected_patient.id)
        rx_query = rx_query.filter(Prescription.patient_id == selected_patient.id)
        doc_query = doc_query.filter(ClinicalDocument.patient_id == selected_patient.id)

    encounters = enc_query.order_by(ClinicalEncounter.visit_date.desc()).all()
    plans = plan_query.order_by(TreatmentPlan.created_at.desc()).all()
    treatments = tr_query.order_by(TreatmentRecord.performed_date.desc()).all()
    prescriptions = rx_query.order_by(Prescription.issue_date.desc()).all()
    documents = doc_query.order_by(ClinicalDocument.created_at.desc()).all()
    services = db.query(Service).order_by(Service.display_order.asc()).all()
    dental_chart = get_patient_dental_chart(db, selected_patient.id) if selected_patient else None

    resp = templates.TemplateResponse(
        request,
        "doctor/workspace.html",
        _base_ctx(
            request,
            db,
            user,
            section=section,
            page_title=f"Doctor Workspace ({section.replace('-', ' ').title()}) — Rumi Dental Care",
            doctor=doctor,
            patients=patients,
            selected_patient=selected_patient,
            appointments=appointments,
            encounters=encounters,
            plans=plans,
            treatments=treatments,
            prescriptions=prescriptions,
            documents=documents,
            services=services,
            dental_chart=dental_chart,
        ),
    )
    if selected_patient:
        resp.set_cookie(
            key="rumi_doctor_patient_id",
            value=str(selected_patient.id),
            max_age=86400,
            path="/",
            samesite="lax",
        )
    return resp


@web_router.get("/doctor/patients/{patient_id}", response_class=HTMLResponse)
def doctor_patient_detail_page(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    redir = _require_web_role(user, ROLE_DOCTOR, staff_login=True)
    if redir:
        return redir

    patient = verify_patient_isolation(db, user, patient_id, request, "patient_profile")
    doctor = db.query(DoctorProfile).filter(DoctorProfile.user_id == user.id).first()
    patients = (
        db.query(PatientProfile)
        .filter(PatientProfile.is_archived.is_(False))
        .order_by(PatientProfile.id.asc())
        .all()
    )
    appointments = (
        db.query(Appointment)
        .filter(Appointment.patient_id == patient.id)
        .order_by(Appointment.appointment_date.desc())
        .all()
    )
    encounters = (
        db.query(ClinicalEncounter)
        .filter(ClinicalEncounter.patient_id == patient.id)
        .order_by(ClinicalEncounter.visit_date.desc())
        .all()
    )
    plans = (
        db.query(TreatmentPlan)
        .filter(TreatmentPlan.patient_id == patient.id)
        .order_by(TreatmentPlan.created_at.desc())
        .all()
    )
    treatments = (
        db.query(TreatmentRecord)
        .filter(TreatmentRecord.patient_id == patient.id)
        .order_by(TreatmentRecord.performed_date.desc())
        .all()
    )
    prescriptions = (
        db.query(Prescription)
        .filter(Prescription.patient_id == patient.id)
        .order_by(Prescription.issue_date.desc())
        .all()
    )
    documents = (
        db.query(ClinicalDocument)
        .filter(ClinicalDocument.patient_id == patient.id)
        .order_by(ClinicalDocument.created_at.desc())
        .all()
    )
    services = db.query(Service).order_by(Service.display_order.asc()).all()
    dental_chart = get_patient_dental_chart(db, patient.id)

    resp = templates.TemplateResponse(
        request,
        "doctor/workspace.html",
        _base_ctx(
            request,
            db,
            user,
            section="patient-detail",
            page_title=f"Patient Clinical File: {patient.full_name} — Rumi Dental Care",
            doctor=doctor,
            patients=patients,
            selected_patient=patient,
            appointments=appointments,
            encounters=encounters,
            plans=plans,
            treatments=treatments,
            prescriptions=prescriptions,
            documents=documents,
            services=services,
            dental_chart=dental_chart,
        ),
    )
    resp.set_cookie(
        key="rumi_doctor_patient_id",
        value=str(patient.id),
        max_age=86400,
        path="/",
        samesite="lax",
    )
    return resp


# ============================================================================
# ADMINISTRATOR DASHBOARD ROUTES (/admin/*)
# ============================================================================


@web_router.get("/admin/dashboard", response_class=HTMLResponse)
@web_router.get("/admin/patients", response_class=HTMLResponse)
@web_router.get("/admin/doctors", response_class=HTMLResponse)
@web_router.get("/admin/staff", response_class=HTMLResponse)
@web_router.get("/admin/appointments", response_class=HTMLResponse)
@web_router.get("/admin/services", response_class=HTMLResponse)
@web_router.get("/admin/treatments", response_class=HTMLResponse)
@web_router.get("/admin/invoices", response_class=HTMLResponse)
@web_router.get("/admin/payments", response_class=HTMLResponse)
@web_router.get("/admin/receipts", response_class=HTMLResponse)
@web_router.get("/admin/reviews", response_class=HTMLResponse)
@web_router.get("/admin/reports", response_class=HTMLResponse)
@web_router.get("/admin/audit-logs", response_class=HTMLResponse)
@web_router.get("/admin/settings", response_class=HTMLResponse)
def admin_dashboard_pages(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_current_user),
):
    redir = _require_web_role(user, ROLE_ADMIN, staff_login=True)
    if redir:
        return redir

    section = request.url.path.split("/admin/")[-1].strip("/") or "dashboard"
    patients = db.query(PatientProfile).order_by(PatientProfile.created_at.desc()).all()
    doctors = db.query(DoctorProfile).order_by(DoctorProfile.id.asc()).all()
    staff_members = db.query(StaffProfile).order_by(StaffProfile.id.asc()).all()
    appointments = (
        db.query(Appointment)
        .order_by(Appointment.appointment_date.desc(), Appointment.start_time.asc())
        .all()
    )
    services = db.query(Service).order_by(Service.display_order.asc()).all()
    treatments = db.query(TreatmentRecord).order_by(TreatmentRecord.performed_date.desc()).all()
    plans = db.query(TreatmentPlan).order_by(TreatmentPlan.created_at.desc()).all()
    invoices = db.query(Invoice).order_by(Invoice.issue_date.desc(), Invoice.id.desc()).all()
    payments = db.query(Payment).order_by(Payment.payment_date.desc(), Payment.id.desc()).all()
    receipts = db.query(Receipt).order_by(Receipt.issued_at.desc(), Receipt.id.desc()).all()
    reviews = db.query(Review).order_by(Review.created_at.desc()).all()
    audit_logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()
    correction_requests = (
        db.query(RecordCorrectionRequest)
        .order_by(RecordCorrectionRequest.created_at.desc())
        .all()
    )

    recorded_payments = [p for p in payments if p.status == "Recorded"]
    total_recorded_revenue = sum((p.amount for p in recorded_payments), Decimal("0.00"))
    outstanding_balance = sum(
        (i.balance_due for i in invoices if i.document_kind == "Invoice" and i.status != "Voided"),
        Decimal("0.00"),
    )

    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        _base_ctx(
            request,
            db,
            user,
            section=section,
            page_title=f"Clinic Administration ({section.replace('-', ' ').title()}) — Rumi Dental Care",
            patients=patients,
            doctors=doctors,
            staff_members=staff_members,
            appointments=appointments,
            services=services,
            treatments=treatments,
            plans=plans,
            invoices=invoices,
            payments=payments,
            receipts=receipts,
            reviews=reviews,
            audit_logs=audit_logs,
            correction_requests=correction_requests,
            total_recorded_revenue=total_recorded_revenue,
            outstanding_balance=outstanding_balance,
        ),
    )
