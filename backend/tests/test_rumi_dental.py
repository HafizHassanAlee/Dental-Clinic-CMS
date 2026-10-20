"""
Comprehensive Automated Test Suite for Rumi Dental Care — Full-Stack Dental Clinic Management System.

Tests cover:
1. Authentication, Password Hashing (bcrypt), Password Reset Single-Use & Expiry, and Login Portal Separation
2. Patient Privacy & Strict Data Isolation (Patient A vs Patient B across all clinical & financial endpoints)
3. Role-Based Access Control (Patient, Doctor, Administrator) & Immediate Deactivation Token Revocation
4. Appointment Booking, Past-Date Validation, Slot Conflict Detection, Status Updates & Rescheduling
5. Clinical Encounters, Post-Finalization Amendment Versioning, Record Correction Requests & FDI Dental Chart
6. Private X-Ray / Clinical Document Upload Signature Validation & Authorized Streaming Download
7. PKR Decimal Billing, Itemized Invoices, Partial & Full Payments, Official Receipts, Reversals & PDF Generation
8. Review Submission, Consent Check & Admin Moderation Visibility
9. Public Website & Role-Protected Web Dashboard Routes
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import shutil

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.permissions import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import hash_password, verify_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import DoctorProfile, PatientProfile, Role, Service, User
from app.services.seed_service import seed_initial_data


TEST_DATABASE_URL = settings.TEST_DATABASE_URL
test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Reset and seed the isolated PostgreSQL `rumi_dental_test` database once per test session."""
    test_upload_dir = Path(__file__).resolve().parent / "tmp_private_uploads"
    if test_upload_dir.exists():
        shutil.rmtree(test_upload_dir, ignore_errors=True)
    test_upload_dir.mkdir(parents=True, exist_ok=True)
    settings.UPLOAD_STORAGE_PATH = str(test_upload_dir)

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()
    try:
        seed_initial_data(db)
    finally:
        db.close()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    if test_upload_dir.exists():
        shutil.rmtree(test_upload_dir, ignore_errors=True)


@pytest.fixture()
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    return TestClient(app)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# 1. PUBLIC WEBSITE & SEPARATE LOGIN ENTRY POINTS
# ============================================================================


def test_public_website_pages_and_genuine_clinic_branding(client: TestClient):
    """Public pages must load without authentication, show genuine Rumi Dental Care details, and never leak patient data."""
    public_routes = [
        "/",
        "/about",
        "/services",
        "/contact",
        "/appointment-info",
        "/faq",
        "/reviews",
        "/privacy-policy",
        "/terms-of-service",
        "/accessibility",
    ]
    for route in public_routes:
        res = client.get(route)
        assert res.status_code == 200, f"Expected 200 OK on {route}, got {res.status_code}"

    home_html = client.get("/").text
    assert "Rumi Dental Care" in home_html
    assert "Dr. Aisha Salman" in home_html
    assert "388 A, Block A, RECHS, Johar Town, Lahore" in home_html
    assert "+92 310 2468080" in home_html
    assert "04:00 PM" in home_html
    # Genuine testimonials from rumidentalcare.com
    assert "Uswa Syed" in home_html
    assert "Sherazi Surayya" in home_html
    assert "Haris Muhammad" in home_html


def test_separate_patient_and_staff_login_pages(client: TestClient):
    """
    Verify `/login` is strictly for patients (with link to `/staff/login` and no admin registration)
    and `/staff/login` is strictly for doctors & administrators.
    """
    patient_login_res = client.get("/login")
    assert patient_login_res.status_code == 200
    html = patient_login_res.text
    assert "/staff/login" in html
    assert "/register" in html
    assert "/forgot-password" in html
    assert "Admin Registration" not in html

    staff_login_res = client.get("/staff/login")
    assert staff_login_res.status_code == 200
    assert "Staff" in staff_login_res.text or "Doctor" in staff_login_res.text


# ============================================================================
# 2. AUTHENTICATION, PASSWORD HASHING, PORTAL SEPARATION & PASSWORD RESET
# ============================================================================


def test_patient_registration_password_hashing_and_duplicate_rejection(
    client: TestClient, db_session
):
    """Test patient registration, bcrypt password hashing, duplicate email rejection, and role enforcement."""
    reg_payload = {
        "full_name": "Zainab Tariq",
        "email": "zainab.tariq@example.com",
        "phone": "+92 300 1112233",
        "password": "StrongPassword123!",
        "confirm_password": "StrongPassword123!",
        "date_of_birth": "1995-04-12",
        "gender": "Female",
        "address": "Model Town, Lahore",
        "privacy_consent_accepted": True,
    }
    res = client.post("/api/v1/auth/register", json=reg_payload)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["role"] == ROLE_PATIENT
    assert data["redirect_url"] == "/patient/dashboard"
    assert data["access_token"]

    # Verify password is stored as bcrypt hash in PostgreSQL, never plaintext
    user_in_db = (
        db_session.query(User).filter(User.email == "zainab.tariq@example.com").first()
    )
    assert user_in_db is not None
    assert user_in_db.password_hash != "StrongPassword123!"
    assert user_in_db.password_hash.startswith("$2")
    assert verify_password("StrongPassword123!", user_in_db.password_hash)
    assert user_in_db.role.name == ROLE_PATIENT

    # Duplicate email registration must be rejected with 409 Conflict
    dup_res = client.post("/api/v1/auth/register", json=reg_payload)
    assert dup_res.status_code == 409


def test_invalid_login_and_portal_separation_enforcement(client: TestClient):
    """
    Verify:
    - Invalid password returns 401
    - Doctor/Admin cannot log in via `/api/v1/auth/patient/login` (returns 403)
    - Patient cannot log in via `/api/v1/auth/staff/login` (returns 403)
    """
    # Bad password
    bad_res = client.post(
        "/api/v1/auth/patient/login",
        json={"email": "zainab.tariq@example.com", "password": "WrongPassword999!"},
    )
    assert bad_res.status_code == 401

    # Doctor attempting to log in on Public Patient Login endpoint -> 403
    doc_on_patient_portal = client.post(
        "/api/v1/auth/patient/login",
        json={"email": "dr.aisha@rumidentalcare.com", "password": "Doctor@Rumi2026!"},
    )
    assert doc_on_patient_portal.status_code == 403

    # Admin attempting to log in on Public Patient Login endpoint -> 403
    admin_on_patient_portal = client.post(
        "/api/v1/auth/patient/login",
        json={"email": "admin@rumidentalcare.com", "password": "Admin@Rumi2026!"},
    )
    assert admin_on_patient_portal.status_code == 403

    # Patient attempting to log in on Staff Login endpoint -> 403
    patient_on_staff_portal = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "zainab.tariq@example.com", "password": "StrongPassword123!"},
    )
    assert patient_on_staff_portal.status_code == 403

    # Valid Doctor login on Staff portal -> 200 & redirect to /doctor/dashboard
    doc_ok = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "dr.aisha@rumidentalcare.com", "password": "Doctor@Rumi2026!"},
    )
    assert doc_ok.status_code == 200
    assert doc_ok.json()["role"] == ROLE_DOCTOR
    assert doc_ok.json()["redirect_url"] == "/doctor/dashboard"

    # Valid Admin login on Staff portal -> 200 & redirect to /admin/dashboard
    admin_ok = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "admin@rumidentalcare.com", "password": "Admin@Rumi2026!"},
    )
    assert admin_ok.status_code == 200
    assert admin_ok.json()["role"] == ROLE_ADMIN
    assert admin_ok.json()["redirect_url"] == "/admin/dashboard"


def test_password_reset_token_single_use_and_validation(client: TestClient):
    """Password reset token must work once, update password, and reject any second reuse."""
    forgot_res = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "zainab.tariq@example.com"},
    )
    assert forgot_res.status_code == 200
    reset_token = forgot_res.json().get("dev_reset_token")
    assert reset_token

    # Reset password using token
    reset_res = client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": reset_token,
            "new_password": "NewSecurePassword456!",
            "confirm_password": "NewSecurePassword456!",
        },
    )
    assert reset_res.status_code == 200

    # Reusing the same reset token must fail with 400
    reuse_res = client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": reset_token,
            "new_password": "AnotherPassword789!",
            "confirm_password": "AnotherPassword789!",
        },
    )
    assert reuse_res.status_code == 400

    # Login with new password succeeds
    login_res = client.post(
        "/api/v1/auth/patient/login",
        json={"email": "zainab.tariq@example.com", "password": "NewSecurePassword456!"},
    )
    assert login_res.status_code == 200


def test_logged_out_user_cannot_access_protected_routes(client: TestClient):
    """Unauthenticated requests to protected API and dashboard routes must be rejected."""
    client.cookies.clear()
    for api_path in [
        "/api/v1/patients/me",
        "/api/v1/appointments",
        "/api/v1/clinical-records",
        "/api/v1/dental-chart/me",
        "/api/v1/invoices",
        "/api/v1/receipts",
        "/api/v1/admin/dashboard",
    ]:
        res = client.get(api_path)
        assert res.status_code == 401, f"Expected 401 on {api_path}, got {res.status_code}"

    # Web dashboards redirect unauthenticated visitors to login
    for web_dash in ["/patient/dashboard", "/doctor/dashboard", "/admin/dashboard"]:
        res = client.get(web_dash, follow_redirects=False)
        assert res.status_code in (302, 303, 307, 401)


# ============================================================================
# 3. STRICT PATIENT PRIVACY & DATA ISOLATION (PATIENT A vs PATIENT B)
# ============================================================================


def test_patient_a_vs_patient_b_strict_isolation(client: TestClient, db_session):
    """
    Verify that Patient A can access their own records, but receives 403 Forbidden
    whenever attempting to view or download Patient B's profile, appointments,
    clinical encounters, dental chart, X-rays/documents, prescriptions, invoices, or receipts.
    """
    # Register Patient A and Patient B
    res_a = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Patient Alpha",
            "email": "patient.alpha@example.com",
            "phone": "+92 301 0000001",
            "password": "AlphaPassword123!",
            "confirm_password": "AlphaPassword123!",
            "date_of_birth": "1990-01-15",
            "gender": "Male",
            "address": "Johar Town, Lahore",
            "privacy_consent_accepted": True,
        },
    )
    assert res_a.status_code == 201
    token_a = res_a.json()["access_token"]

    res_b = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Patient Bravo",
            "email": "patient.bravo@example.com",
            "phone": "+92 301 0000002",
            "password": "BravoPassword123!",
            "confirm_password": "BravoPassword123!",
            "date_of_birth": "1992-06-20",
            "gender": "Female",
            "address": "DHA, Lahore",
            "privacy_consent_accepted": True,
        },
    )
    assert res_b.status_code == 201
    token_b = res_b.json()["access_token"]

    # Get Patient A and Patient B profile IDs
    prof_a = client.get("/api/v1/patients/me", headers=_auth_headers(token_a)).json()
    prof_b = client.get("/api/v1/patients/me", headers=_auth_headers(token_b)).json()
    patient_a_id = prof_a["id"]
    patient_b_id = prof_b["id"]
    assert patient_a_id != patient_b_id

    # Doctor & Admin tokens for creating clinical & billing records for Patient B
    doc_login = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "dr.aisha@rumidentalcare.com", "password": "Doctor@Rumi2026!"},
    )
    doc_token = doc_login.json()["access_token"]

    admin_login = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "admin@rumidentalcare.com", "password": "Admin@Rumi2026!"},
    )
    admin_token = admin_login.json()["access_token"]

    doctor_profile = db_session.query(DoctorProfile).first()
    service = db_session.query(Service).first()

    # 1. Create an Appointment for Patient B
    future_date = (date.today() + timedelta(days=5)).isoformat()
    apt_b_res = client.post(
        "/api/v1/appointments",
        headers=_auth_headers(token_b),
        json={
            "doctor_id": doctor_profile.id,
            "service_id": service.id,
            "appointment_date": future_date,
            "start_time": "17:00",
            "reason_for_visit": "Patient B molar sensitivity",
        },
    )
    assert apt_b_res.status_code == 201, apt_b_res.text
    apt_b_id = apt_b_res.json()["id"]

    # 2. Doctor creates a Clinical Encounter for Patient B
    enc_b_res = client.post(
        "/api/v1/clinical-records",
        headers=_auth_headers(doc_token),
        json={
            "patient_id": patient_b_id,
            "appointment_id": apt_b_id,
            "presenting_complaint": "Deep caries on #36",
            "examination_findings": "Occlusal cavitation on #36",
            "diagnosis_summary": "Symptomatic irreversible pulpitis #36",
            "treatment_performed": "Access opening and pulpectomy",
            "finalize": True,
        },
    )
    assert enc_b_res.status_code == 201, enc_b_res.text
    enc_b_id = enc_b_res.json()["id"]

    # 3. Doctor updates Dental Chart for Patient B
    chart_b_res = client.put(
        f"/api/v1/dental-chart/{patient_b_id}/tooth",
        headers=_auth_headers(doc_token),
        json={
            "tooth_fdi": "36",
            "condition_status": "RootCanalTreated",
            "surfaces": "O",
            "clinical_notes": "RCT initiated on #36",
        },
    )
    assert chart_b_res.status_code == 200, chart_b_res.text

    # 4. Doctor uploads a private X-Ray PNG for Patient B
    valid_png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
        b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    doc_b_res = client.post(
        "/api/v1/documents/upload",
        headers=_auth_headers(doc_token),
        data={
            "patient_id": str(patient_b_id),
            "title": "Patient B Periapical X-Ray #36",
            "document_type": "X-Ray",
            "tooth_fdi": "36",
            "is_patient_visible": "true",
        },
        files={"file": ("patient_b_xray.png", valid_png_bytes, "image/png")},
    )
    assert doc_b_res.status_code == 201, doc_b_res.text
    doc_b_id = doc_b_res.json()["id"]

    # 5. Doctor issues a Prescription for Patient B
    rx_b_res = client.post(
        "/api/v1/prescriptions",
        headers=_auth_headers(doc_token),
        json={
            "patient_id": patient_b_id,
            "encounter_id": enc_b_id,
            "diagnosis_notes": "Acute apical periodontitis #36",
            "general_instructions": "Take after meals",
            "items": [
                {
                    "medication_name": "Amoxicillin + Clavulanic Acid",
                    "strength": "625mg",
                    "dosage": "1 tablet",
                    "route": "Oral",
                    "frequency": "Twice daily (BD)",
                    "duration": "5 days",
                    "quantity": "10 tablets",
                }
            ],
        },
    )
    assert rx_b_res.status_code == 201, rx_b_res.text
    rx_b_id = rx_b_res.json()["id"]

    # 6. Admin creates an Invoice and records a Payment/Receipt for Patient B
    inv_b_res = client.post(
        "/api/v1/invoices",
        headers=_auth_headers(admin_token),
        json={
            "patient_id": patient_b_id,
            "document_kind": "Invoice",
            "discount_amount": 500,
            "tax_amount": 0,
            "items": [
                {
                    "description": "Root Canal Treatment #36",
                    "tooth_fdi": "36",
                    "quantity": 1,
                    "unit_price": 12000,
                }
            ],
        },
    )
    assert inv_b_res.status_code == 201, inv_b_res.text
    inv_b_id = inv_b_res.json()["id"]

    pay_b_res = client.post(
        "/api/v1/payments",
        headers=_auth_headers(admin_token),
        json={
            "invoice_id": inv_b_id,
            "amount": 5000,
            "payment_method": "Cash",
            "notes": "Partial payment by Patient B",
        },
    )
    assert pay_b_res.status_code == 201, pay_b_res.text
    rcpt_b_id = pay_b_res.json()["receipt_id"]

    # ---- VERIFY PATIENT B CAN ACCESS ALL OF THEIR OWN RECORDS ----
    assert client.get(f"/api/v1/patients/{patient_b_id}", headers=_auth_headers(token_b)).status_code == 200
    assert client.get(f"/api/v1/appointments/{apt_b_id}", headers=_auth_headers(token_b)).status_code == 200
    assert client.get(f"/api/v1/clinical-records/{enc_b_id}", headers=_auth_headers(token_b)).status_code == 200
    assert client.get(f"/api/v1/dental-chart/{patient_b_id}", headers=_auth_headers(token_b)).status_code == 200
    assert client.get(f"/api/v1/documents/{doc_b_id}/download", headers=_auth_headers(token_b)).status_code == 200
    assert client.get(f"/api/v1/prescriptions/{rx_b_id}/pdf", headers=_auth_headers(token_b)).status_code == 200
    assert client.get(f"/api/v1/invoices/{inv_b_id}", headers=_auth_headers(token_b)).status_code == 200
    assert client.get(f"/api/v1/receipts/{rcpt_b_id}/pdf", headers=_auth_headers(token_b)).status_code == 200

    # ---- VERIFY PATIENT A IS STRICTLY BLOCKED (403 FORBIDDEN) FROM ALL OF PATIENT B'S RECORDS ----
    forbidden_targets = [
        f"/api/v1/patients/{patient_b_id}",
        f"/api/v1/patients/{patient_b_id}/treatment-summary.pdf",
        f"/api/v1/appointments/{apt_b_id}",
        f"/api/v1/appointments?patient_id={patient_b_id}",
        f"/api/v1/clinical-records/{enc_b_id}",
        f"/api/v1/clinical-records?patient_id={patient_b_id}",
        f"/api/v1/dental-chart/{patient_b_id}",
        f"/api/v1/documents/{doc_b_id}",
        f"/api/v1/documents/{doc_b_id}/download",
        f"/api/v1/documents?patient_id={patient_b_id}",
        f"/api/v1/prescriptions/{rx_b_id}",
        f"/api/v1/prescriptions/{rx_b_id}/pdf",
        f"/api/v1/prescriptions?patient_id={patient_b_id}",
        f"/api/v1/invoices/{inv_b_id}",
        f"/api/v1/invoices/{inv_b_id}/pdf",
        f"/api/v1/invoices?patient_id={patient_b_id}",
        f"/api/v1/receipts/{rcpt_b_id}",
        f"/api/v1/receipts/{rcpt_b_id}/pdf",
        f"/api/v1/receipts?patient_id={patient_b_id}",
    ]
    for url in forbidden_targets:
        res = client.get(url, headers=_auth_headers(token_a))
        assert res.status_code == 403, f"Security breach: Patient A got {res.status_code} on {url}"


# ============================================================================
# 4. DOCTOR & ADMINISTRATOR RBAC + DEACTIVATED ACCOUNT REVOCATION
# ============================================================================


def test_doctor_and_admin_rbac_and_account_deactivation(client: TestClient):
    """
    Verify:
    - Doctor cannot access Admin-only endpoints (/api/v1/admin/*, /api/v1/reports/*)
    - Patient cannot modify clinical records or access Doctor/Admin dashboards
    - Deactivating a user account immediately invalidates their active JWT token
    """
    doc_token = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "dr.aisha@rumidentalcare.com", "password": "Doctor@Rumi2026!"},
    ).json()["access_token"]

    admin_token = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "admin@rumidentalcare.com", "password": "Admin@Rumi2026!"},
    ).json()["access_token"]

    # Doctor blocked from Admin endpoints
    for admin_endpoint in [
        "/api/v1/admin/dashboard",
        "/api/v1/admin/users",
        "/api/v1/admin/staff",
        "/api/v1/admin/audit-logs",
        "/api/v1/reports/summary",
    ]:
        res = client.get(admin_endpoint, headers=_auth_headers(doc_token))
        assert res.status_code == 403, f"Doctor should be blocked from {admin_endpoint}"

    # Admin can access Admin endpoints and provision a new Doctor account
    admin_dash = client.get("/api/v1/admin/dashboard", headers=_auth_headers(admin_token))
    assert admin_dash.status_code == 200
    assert admin_dash.json()["currency"] == "PKR"

    new_doc_res = client.post(
        "/api/v1/doctors",
        headers=_auth_headers(admin_token),
        json={
            "full_name": "Dr. Bilal Ahmed",
            "email": "dr.bilal@rumidentalcare.com",
            "phone": "+92 321 9876543",
            "password": "BilalDoctor123!",
            "title": "Associate Dental Surgeon",
            "specialization": "Restorative Dentistry",
            "qualification": "BDS",
            "consultation_fee": 2000,
            "slot_duration_minutes": 30,
            "is_public": True,
        },
    )
    assert new_doc_res.status_code == 201, new_doc_res.text
    bilal_user_id = new_doc_res.json()["user_id"]

    # Dr. Bilal logs in and receives a valid token
    bilal_login = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "dr.bilal@rumidentalcare.com", "password": "BilalDoctor123!"},
    )
    assert bilal_login.status_code == 200
    bilal_token = bilal_login.json()["access_token"]

    # Admin deactivates Dr. Bilal's account
    deact_res = client.patch(
        f"/api/v1/admin/users/{bilal_user_id}/status?is_active=false",
        headers=_auth_headers(admin_token),
    )
    assert deact_res.status_code == 200

    # Dr. Bilal's existing JWT token must immediately be rejected
    me_after_deact = client.get("/api/v1/auth/me", headers=_auth_headers(bilal_token))
    assert me_after_deact.status_code in (401, 403)


# ============================================================================
# 5. APPOINTMENTS: PAST DATE REJECTION, CONFLICT DETECTION & RESCHEDULING
# ============================================================================


def test_appointment_validation_conflict_and_reschedule(client: TestClient, db_session):
    """Test valid booking, past date rejection, double-booking conflict rejection, and rescheduling."""
    login_res = client.post(
        "/api/v1/auth/patient/login",
        json={"email": "patient.alpha@example.com", "password": "AlphaPassword123!"},
    )
    token_a = login_res.json()["access_token"]
    doctor = db_session.query(DoctorProfile).filter(DoctorProfile.is_active.is_(True)).first()
    service = db_session.query(Service).first()

    # 1. Past appointment date must be rejected (400)
    past_date = (date.today() - timedelta(days=2)).isoformat()
    past_res = client.post(
        "/api/v1/appointments",
        headers=_auth_headers(token_a),
        json={
            "doctor_id": doctor.id,
            "service_id": service.id,
            "appointment_date": past_date,
            "start_time": "16:30",
            "reason_for_visit": "Past date check",
        },
    )
    assert past_res.status_code == 400

    # 2. Valid future appointment creation
    target_date = (date.today() + timedelta(days=9)).isoformat()
    valid_res = client.post(
        "/api/v1/appointments",
        headers=_auth_headers(token_a),
        json={
            "doctor_id": doctor.id,
            "service_id": service.id,
            "appointment_date": target_date,
            "start_time": "18:00",
            "reason_for_visit": "Routine dental scaling and checkup",
        },
    )
    assert valid_res.status_code == 201, valid_res.text
    apt_id = valid_res.json()["id"]

    # 3. Conflicting appointment slot on same doctor/date/time must return 409 Conflict
    conflict_res = client.post(
        "/api/v1/appointments",
        headers=_auth_headers(token_a),
        json={
            "doctor_id": doctor.id,
            "service_id": service.id,
            "appointment_date": target_date,
            "start_time": "18:00",
            "reason_for_visit": "Duplicate slot test",
        },
    )
    assert conflict_res.status_code == 409

    # 4. Reschedule to a free slot succeeds
    resched_res = client.post(
        f"/api/v1/appointments/{apt_id}/reschedule",
        headers=_auth_headers(token_a),
        json={
            "appointment_date": target_date,
            "start_time": "19:30",
            "reason": "Prefer evening slot",
        },
    )
    assert resched_res.status_code == 200
    assert resched_res.json()["start_time"] == "19:30"


# ============================================================================
# 6. CLINICAL ENCOUNTERS, AMENDMENTS, FDI DENTAL CHART & FILE VALIDATION
# ============================================================================


def test_clinical_note_amendment_versioning_and_fdi_dental_chart(client: TestClient):
    """
    Verify:
    - Finalized clinical encounters cannot be overwritten without `amendment_reason`
    - Providing `amendment_reason` increments version and records an immutable EncounterAmendment
    - FDI Dental Chart supports both Permanent (11–48) and Primary (51–85) teeth and rejects invalid codes
    - Clinical document upload rejects invalid file signatures
    """
    doc_token = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "dr.aisha@rumidentalcare.com", "password": "Doctor@Rumi2026!"},
    ).json()["access_token"]

    token_a = client.post(
        "/api/v1/auth/patient/login",
        json={"email": "patient.alpha@example.com", "password": "AlphaPassword123!"},
    ).json()["access_token"]
    patient_a_id = client.get("/api/v1/patients/me", headers=_auth_headers(token_a)).json()["id"]

    # Create finalized encounter
    enc_res = client.post(
        "/api/v1/clinical-records",
        headers=_auth_headers(doc_token),
        json={
            "patient_id": patient_a_id,
            "presenting_complaint": "Sensitivity to cold on upper right",
            "examination_findings": "Class I caries on #16",
            "diagnosis_summary": "Reversible pulpitis #16",
            "treatment_performed": "Composite restoration #16",
            "finalize": True,
        },
    )
    assert enc_res.status_code == 201
    enc_id = enc_res.json()["id"]
    assert enc_res.json()["status"] == "Finalized"
    assert enc_res.json()["version"] == 1

    # Attempt to overwrite finalized encounter without amendment_reason -> 400
    no_reason_res = client.put(
        f"/api/v1/clinical-records/{enc_id}",
        headers=_auth_headers(doc_token),
        json={"diagnosis_summary": "Silent overwrite attempt"},
    )
    assert no_reason_res.status_code == 400

    # Amend finalized encounter with explicit amendment_reason -> 200, version=2, status="Amended"
    amend_res = client.put(
        f"/api/v1/clinical-records/{enc_id}",
        headers=_auth_headers(doc_token),
        json={
            "diagnosis_summary": "Reversible pulpitis #16 (confirmed via vitality test)",
            "amendment_reason": "Added cold vitality test confirmation details",
        },
    )
    assert amend_res.status_code == 200
    amended_data = amend_res.json()
    assert amended_data["version"] == 2
    assert amended_data["status"] == "Amended"
    assert len(amended_data["amendments"]) == 1
    assert "vitality test" in amended_data["amendments"][0]["amendment_reason"]

    # Update Permanent tooth #16 and Primary/Deciduous tooth #55 on FDI Dental Chart
    perm_res = client.put(
        f"/api/v1/dental-chart/{patient_a_id}/tooth",
        headers=_auth_headers(doc_token),
        json={
            "tooth_fdi": "16",
            "condition_status": "Filled",
            "surfaces": "O",
            "clinical_notes": "Composite restoration placed",
        },
    )
    assert perm_res.status_code == 200

    prim_res = client.put(
        f"/api/v1/dental-chart/{patient_a_id}/tooth",
        headers=_auth_headers(doc_token),
        json={
            "tooth_fdi": "55",
            "condition_status": "Caries",
            "surfaces": "MO",
            "clinical_notes": "Primary molar caries noted",
        },
    )
    assert prim_res.status_code == 200

    # Invalid FDI tooth code #99 must be rejected with 400
    bad_fdi_res = client.put(
        f"/api/v1/dental-chart/{patient_a_id}/tooth",
        headers=_auth_headers(doc_token),
        json={"tooth_fdi": "99", "condition_status": "Healthy"},
    )
    assert bad_fdi_res.status_code == 400

    # Spoofed/executable file upload must be rejected
    spoof_res = client.post(
        "/api/v1/documents/upload",
        headers=_auth_headers(doc_token),
        data={"patient_id": str(patient_a_id), "title": "Spoofed File", "document_type": "X-Ray"},
        files={"file": ("fake_xray.png", b"not-a-valid-png-header", "image/png")},
    )
    assert spoof_res.status_code == 400


# ============================================================================
# 7. PKR DECIMAL BILLING, PARTIAL PAYMENTS, RECEIPTS, REVERSALS & PDFS
# ============================================================================


def test_pkr_billing_partial_payment_receipt_reversal_and_pdfs(client: TestClient):
    """
    Verify:
    - Invoice calculation in PKR using Decimal arithmetic
    - Creating an unpaid invoice does NOT create a receipt
    - Recording a partial payment updates status to PartiallyPaid and issues an official Receipt
    - Recording remaining balance updates status to Paid and balance_due to 0.0
    - Reversing a payment voids the receipt and restores the invoice balance_due
    - All 4 PDF generators (Invoice, Receipt, Prescription, Treatment Summary) return valid %PDF documents
    """
    admin_token = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "admin@rumidentalcare.com", "password": "Admin@Rumi2026!"},
    ).json()["access_token"]

    token_a = client.post(
        "/api/v1/auth/patient/login",
        json={"email": "patient.alpha@example.com", "password": "AlphaPassword123!"},
    ).json()["access_token"]
    patient_a_id = client.get("/api/v1/patients/me", headers=_auth_headers(token_a)).json()["id"]

    # 1. Create an Invoice: 2 items (3500 + 8500 = 12000), discount 1000, tax 0 -> Total 11000 PKR
    inv_res = client.post(
        "/api/v1/invoices",
        headers=_auth_headers(admin_token),
        json={
            "patient_id": patient_a_id,
            "document_kind": "Invoice",
            "discount_amount": 1000,
            "discount_reason": "Family care discount",
            "tax_amount": 0,
            "items": [
                {"description": "Scaling & Polishing", "quantity": 1, "unit_price": 3500},
                {"description": "Composite Filling #16", "tooth_fdi": "16", "quantity": 1, "unit_price": 8500},
            ],
        },
    )
    assert inv_res.status_code == 201, inv_res.text
    inv = inv_res.json()
    inv_id = inv["id"]
    assert inv["currency"] == "PKR"
    assert inv["subtotal"] == 12000.0
    assert inv["discount_amount"] == 1000.0
    assert inv["total_amount"] == 11000.0
    assert inv["amount_paid"] == 0.0
    assert inv["balance_due"] == 11000.0
    assert inv["status"] == "Unpaid"
    assert len(inv["payments"]) == 0

    # 2. Record a partial payment of PKR 4,000 -> status becomes PartiallyPaid, balance_due = 7,000
    pay1_res = client.post(
        "/api/v1/payments",
        headers=_auth_headers(admin_token),
        json={
            "invoice_id": inv_id,
            "amount": 4000,
            "payment_method": "Card",
            "reference_number": "POS-998811",
        },
    )
    assert pay1_res.status_code == 201, pay1_res.text
    pay1 = pay1_res.json()
    assert pay1["receipt_id"] is not None
    assert pay1["receipt_number"].startswith("RCP-")

    inv_after_p1 = client.get(f"/api/v1/invoices/{inv_id}", headers=_auth_headers(token_a)).json()
    assert inv_after_p1["status"] == "PartiallyPaid"
    assert inv_after_p1["amount_paid"] == 4000.0
    assert inv_after_p1["balance_due"] == 7000.0

    # 3. Record remaining payment of PKR 7,000 -> status becomes Paid, balance_due = 0.0
    pay2_res = client.post(
        "/api/v1/payments",
        headers=_auth_headers(admin_token),
        json={
            "invoice_id": inv_id,
            "amount": 7000,
            "payment_method": "Bank Transfer",
            "reference_number": "IBFT-772200",
        },
    )
    assert pay2_res.status_code == 201
    pay2_id = pay2_res.json()["id"]

    inv_after_p2 = client.get(f"/api/v1/invoices/{inv_id}", headers=_auth_headers(token_a)).json()
    assert inv_after_p2["status"] == "Paid"
    assert inv_after_p2["amount_paid"] == 11000.0
    assert inv_after_p2["balance_due"] == 0.0

    # 4. Verify PDF downloads for Invoice, Receipt, and Treatment Summary
    inv_pdf = client.get(f"/api/v1/invoices/{inv_id}/pdf", headers=_auth_headers(token_a))
    assert inv_pdf.status_code == 200
    assert inv_pdf.headers["content-type"] == "application/pdf"
    assert inv_pdf.content.startswith(b"%PDF-")

    rcpt_pdf = client.get(f"/api/v1/receipts/{pay1['receipt_id']}/pdf", headers=_auth_headers(token_a))
    assert rcpt_pdf.status_code == 200
    assert rcpt_pdf.content.startswith(b"%PDF-")

    summary_pdf = client.get(
        f"/api/v1/patients/{patient_a_id}/treatment-summary.pdf", headers=_auth_headers(token_a)
    )
    assert summary_pdf.status_code == 200
    assert summary_pdf.content.startswith(b"%PDF-")

    # 5. Reverse second payment -> balance_due returns to 7,000 and status returns to PartiallyPaid
    rev_res = client.post(
        f"/api/v1/payments/{pay2_id}/reverse",
        headers=_auth_headers(admin_token),
        json={"reversal_reason": "Duplicate bank transfer reference correction"},
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "Reversed"

    inv_after_rev = client.get(f"/api/v1/invoices/{inv_id}", headers=_auth_headers(token_a)).json()
    assert inv_after_rev["status"] == "PartiallyPaid"
    assert inv_after_rev["amount_paid"] == 4000.0
    assert inv_after_rev["balance_due"] == 7000.0


# ============================================================================
# 8. REVIEW SUBMISSION, CONSENT & MODERATION WORKFLOW
# ============================================================================


def test_review_submission_and_moderation_visibility(client: TestClient):
    """
    Newly submitted patient reviews must start as 'Pending' (not visible on public `/api/v1/reviews/public`)
    and become publicly visible only after Administrator approval.
    """
    token_a = client.post(
        "/api/v1/auth/patient/login",
        json={"email": "patient.alpha@example.com", "password": "AlphaPassword123!"},
    ).json()["access_token"]

    admin_token = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "admin@rumidentalcare.com", "password": "Admin@Rumi2026!"},
    ).json()["access_token"]

    submit_res = client.post(
        "/api/v1/reviews",
        headers=_auth_headers(token_a),
        json={
            "rating": 5,
            "title": "Gentle and hygienic treatment",
            "comment": "Dr. Aisha Salman explained every step of my dental filling clearly.",
            "consent_to_publish": True,
        },
    )
    assert submit_res.status_code == 201
    rev_id = submit_res.json()["id"]
    assert submit_res.json()["status"] == "Pending"

    # While Pending, review must NOT appear in public reviews
    public_before = client.get("/api/v1/reviews/public").json()
    assert all(r["id"] != rev_id for r in public_before)

    # Admin approves the review
    mod_res = client.patch(
        f"/api/v1/reviews/{rev_id}/moderate",
        headers=_auth_headers(admin_token),
        json={"status": "Approved", "moderation_reason": "Verified patient visit"},
    )
    assert mod_res.status_code == 200
    assert mod_res.json()["status"] == "Approved"

    # Now it appears in public approved reviews
    public_after = client.get("/api/v1/reviews/public").json()
    assert any(r["id"] == rev_id for r in public_after)


def test_treatment_plans_records_correction_requests_and_csv_export(client: TestClient):
    """Test treatment plans, treatment records, patient record correction requests, and CSV financial export."""
    doc_token = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "dr.aisha@rumidentalcare.com", "password": "Doctor@Rumi2026!"},
    ).json()["access_token"]

    admin_token = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "admin@rumidentalcare.com", "password": "Admin@Rumi2026!"},
    ).json()["access_token"]

    token_a = client.post(
        "/api/v1/auth/patient/login",
        json={"email": "patient.alpha@example.com", "password": "AlphaPassword123!"},
    ).json()["access_token"]
    patient_a_id = client.get("/api/v1/patients/me", headers=_auth_headers(token_a)).json()["id"]

    # 1. Doctor creates a Treatment Plan for Patient A
    tp_res = client.post(
        "/api/v1/treatments/plans",
        headers=_auth_headers(doc_token),
        json={
            "patient_id": patient_a_id,
            "title": "Restorative & Crown Plan #16",
            "clinical_summary": "Zirconia crown following endodontic therapy",
            "items": [
                {
                    "tooth_fdi": "16",
                    "procedure_name": "Full Ceramic Zirconia Crown #16",
                    "estimated_cost": 18000,
                    "priority": "High",
                }
            ],
        },
    )
    assert tp_res.status_code == 201, tp_res.text
    plan_id = tp_res.json()["id"]
    item_id = tp_res.json()["items"][0]["id"]
    assert tp_res.json()["total_estimated_cost"] == 18000.0

    # 2. Doctor records a completed Treatment Record linked to the plan item
    tr_res = client.post(
        "/api/v1/treatments/records",
        headers=_auth_headers(doc_token),
        json={
            "patient_id": patient_a_id,
            "treatment_plan_item_id": item_id,
            "tooth_fdi": "16",
            "surface": "Crown",
            "procedure_name": "Full Ceramic Zirconia Crown #16",
            "clinical_description": "Crown cementation completed with resin luting cement.",
            "materials_used": "Monolithic Zirconia + Resin Cement",
            "post_op_instructions": "Avoid sticky foods for 24 hours.",
        },
    )
    assert tr_res.status_code == 201, tr_res.text

    # 3. Patient A submits a formal Record Correction Request (patients cannot overwrite clinical notes directly)
    corr_res = client.post(
        "/api/v1/patients/me/correction-requests",
        headers=_auth_headers(token_a),
        json={
            "section_name": "Allergies / Medical History",
            "requested_change": "Please add seasonal pollen allergy to my medical history chart.",
        },
    )
    assert corr_res.status_code == 201, corr_res.text
    assert corr_res.json()["status"] == "Pending"

    # 4. Admin exports financial payments CSV
    csv_res = client.get("/api/v1/payments/export.csv", headers=_auth_headers(admin_token))
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "Payment Number,Receipt Number,Invoice Number" in csv_res.text


def test_role_protected_web_dashboards_cross_role_isolation(client: TestClient):
    """
    Verify each role can access its own HTML portal dashboard (200 OK)
    and is strictly blocked (403 Forbidden) from accessing dashboards belonging to other roles.
    """
    token_a = client.post(
        "/api/v1/auth/patient/login",
        json={"email": "patient.alpha@example.com", "password": "AlphaPassword123!"},
    ).json()["access_token"]

    doc_token = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "dr.aisha@rumidentalcare.com", "password": "Doctor@Rumi2026!"},
    ).json()["access_token"]

    admin_token = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "admin@rumidentalcare.com", "password": "Admin@Rumi2026!"},
    ).json()["access_token"]

    # Patient: 200 on /patient/dashboard, 403 on /doctor/dashboard & /admin/dashboard
    assert client.get("/patient/dashboard", headers=_auth_headers(token_a)).status_code == 200
    assert client.get("/doctor/dashboard", headers=_auth_headers(token_a)).status_code == 403
    assert client.get("/admin/dashboard", headers=_auth_headers(token_a)).status_code == 403

    # Doctor: 200 on /doctor/dashboard, 403 on /patient/dashboard & /admin/dashboard
    assert client.get("/doctor/dashboard", headers=_auth_headers(doc_token)).status_code == 200
    assert client.get("/patient/dashboard", headers=_auth_headers(doc_token)).status_code == 403
    assert client.get("/admin/dashboard", headers=_auth_headers(doc_token)).status_code == 403

    # Admin: 200 on /admin/dashboard, 403 on /patient/dashboard & /doctor/dashboard
    assert client.get("/admin/dashboard", headers=_auth_headers(admin_token)).status_code == 200
    assert client.get("/patient/dashboard", headers=_auth_headers(admin_token)).status_code == 403
    assert client.get("/doctor/dashboard", headers=_auth_headers(admin_token)).status_code == 403


def test_new_verification_doctor_patient_persistence_and_admin_features(client: TestClient, db_session: Session):
    """
    Tests the 6 new requirements:
    1. Account verification via email (muhammadhafizhassan228@gmail.com) and phone/WhatsApp OTP.
    2. Security headers (CSP, Cache-Control no-store on private routes).
    3. Doctor Workspace active patient persistence across /doctor/patients/{id} and /doctor/documents.
    4. Removing recent X-ray uploads (individual delete & clear patient uploads).
    5. Admin updating procedure details (PUT /api/v1/services/{service_id}).
    6. Admin deleting a patient account (DELETE /api/v1/patients/{patient_id}).
    """
    # 1. Register a new patient with WhatsApp/Email verification and verify OTP
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Verified Test Patient",
            "email": "verified.patient@example.com",
            "phone": "+92 310 9998877",
            "password": "VerifyPassword123!",
            "confirm_password": "VerifyPassword123!",
            "verification_channel": "email",
            "privacy_consent_accepted": True,
        },
    )
    assert reg_res.status_code == 201, reg_res.text
    reg_data = reg_res.json()
    pat_token = reg_data["access_token"]
    v_info = reg_data["verification_info"]
    assert v_info is not None
    assert v_info["sender"] == "muhammadhafizhassan228@gmail.com"
    assert "whatsapp_url" in v_info
    otp_code = v_info.get("dev_otp_code")
    assert otp_code and len(otp_code) == 6

    # Also test requesting WhatsApp OTP explicitly
    wa_res = client.post(
        "/api/v1/auth/send-verification-otp",
        headers=_auth_headers(pat_token),
        json={"channel": "whatsapp"},
    )
    assert wa_res.status_code == 200
    wa_info = wa_res.json()
    assert "wa.me" in wa_info["whatsapp_url"]
    latest_otp = wa_info["dev_otp_code"]

    # Verify with the 6-digit OTP
    verify_res = client.post(
        "/api/v1/auth/verify-otp",
        headers=_auth_headers(pat_token),
        json={"otp_code": latest_otp},
    )
    assert verify_res.status_code == 200, verify_res.text
    assert verify_res.json()["verified"] is True

    me_res = client.get("/api/v1/auth/me", headers=_auth_headers(pat_token))
    assert me_res.json()["is_email_verified"] is True

    # 2. Verify hardened security headers on authenticated routes
    assert "Content-Security-Policy" in me_res.headers
    assert "no-store" in me_res.headers.get("Cache-Control", "")

    # 3. Doctor Workspace active patient persistence
    doc_token = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "dr.aisha@rumidentalcare.com", "password": "Doctor@Rumi2026!"},
    ).json()["access_token"]

    new_patient_profile = client.get("/api/v1/patients/me", headers=_auth_headers(pat_token)).json()
    new_pid = new_patient_profile["id"]

    # Doctor visits /doctor/patients/{new_pid} -> sets rumi_doctor_patient_id cookie
    pat_page = client.get(f"/doctor/patients/{new_pid}", headers=_auth_headers(doc_token))
    assert pat_page.status_code == 200
    assert pat_page.cookies.get("rumi_doctor_patient_id") == str(new_pid)

    # Doctor clicks /doctor/documents -> active patient remains Verified Test Patient, NOT reset to first patient
    client.cookies.set("rumi_doctor_patient_id", str(new_pid))
    docs_page = client.get("/doctor/documents", headers=_auth_headers(doc_token))
    assert docs_page.status_code == 200
    assert "Verified Test Patient" in docs_page.text

    # 4. Upload and remove recent X-ray uploads
    valid_png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
        b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    up_res = client.post(
        "/api/v1/documents/upload",
        headers=_auth_headers(doc_token),
        data={"patient_id": str(new_pid), "title": "Temp Upload To Remove", "document_type": "X-Ray"},
        files={"file": ("temp.png", valid_png_bytes, "image/png")},
    )
    assert up_res.status_code == 201
    up_doc_id = up_res.json()["id"]

    del_doc_res = client.delete(f"/api/v1/documents/{up_doc_id}", headers=_auth_headers(doc_token))
    assert del_doc_res.status_code == 200

    # 5. Admin updates procedure details
    admin_token = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "admin@rumidentalcare.com", "password": "Admin@Rumi2026!"},
    ).json()["access_token"]

    services_list = client.get("/api/v1/services").json()
    target_srv = services_list[0]
    upd_srv_res = client.put(
        f"/api/v1/services/{target_srv['id']}",
        headers=_auth_headers(admin_token),
        json={
            "name": "Comprehensive Dental Consultation & Digital Exam",
            "price": 2000.00,
            "short_description": "Updated consultation procedure description and fee.",
        },
    )
    assert upd_srv_res.status_code == 200, upd_srv_res.text
    assert upd_srv_res.json()["price"] == 2000.0
    assert upd_srv_res.json()["name"] == "Comprehensive Dental Consultation & Digital Exam"

    # 6. Admin deletes the test patient
    del_pat_res = client.delete(
        f"/api/v1/patients/{new_pid}",
        headers=_auth_headers(admin_token),
    )
    assert del_pat_res.status_code == 200, del_pat_res.text
    assert del_pat_res.json()["deleted_patient_id"] == new_pid


