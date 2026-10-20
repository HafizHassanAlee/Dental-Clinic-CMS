from typing import Dict, List

ROLE_PATIENT = "patient"
ROLE_DOCTOR = "doctor"
ROLE_ADMIN = "admin"

ALL_ROLES = [ROLE_PATIENT, ROLE_DOCTOR, ROLE_ADMIN]

PERMISSIONS_CATALOG: Dict[str, str] = {
    "patient:portal_access": "Access authenticated patient portal and own records",
    "patient:book_appointment": "Request, view, cancel, or reschedule own appointments",
    "patient:submit_review": "Submit and manage own clinic review",
    "clinical:view_patients": "View authorized patient profiles and clinical histories",
    "clinical:write_encounters": "Record clinical consultations, examinations, and diagnoses",
    "clinical:manage_dental_chart": "Update FDI dental chart findings and tooth history",
    "clinical:manage_treatments": "Create and update treatment plans and treatment records",
    "clinical:issue_prescriptions": "Issue and sign clinical prescriptions",
    "clinical:upload_documents": "Upload and manage clinical documents and X-rays",
    "admin:manage_users": "Create, activate, deactivate, and manage patients, doctors, and staff",
    "admin:manage_schedules": "Configure clinic schedules, doctor availability, and appointments",
    "admin:manage_services": "Manage service catalog and fee schedule",
    "admin:manage_billing": "Create invoices, record payments, issue receipts, and reverse payments",
    "admin:moderate_reviews": "Approve, reject, or hide patient reviews",
    "admin:view_reports": "Access clinic operational and financial analytics",
    "admin:view_audit_logs": "Inspect security and clinical audit logs",
    "admin:manage_settings": "Configure clinic branding, contact information, and hours",
    "admin:view_clinical_records": "Explicit permission to inspect clinical encounters for administration",
}

ROLE_DEFAULT_PERMISSIONS: Dict[str, List[str]] = {
    ROLE_PATIENT: [
        "patient:portal_access",
        "patient:book_appointment",
        "patient:submit_review",
    ],
    ROLE_DOCTOR: [
        "clinical:view_patients",
        "clinical:write_encounters",
        "clinical:manage_dental_chart",
        "clinical:manage_treatments",
        "clinical:issue_prescriptions",
        "clinical:upload_documents",
    ],
    ROLE_ADMIN: [
        "admin:manage_users",
        "admin:manage_schedules",
        "admin:manage_services",
        "admin:manage_billing",
        "admin:moderate_reviews",
        "admin:view_reports",
        "admin:view_audit_logs",
        "admin:manage_settings",
        "admin:view_clinical_records",
        "clinical:view_patients",
    ],
}
