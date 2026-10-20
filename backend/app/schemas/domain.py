from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ============================================================================
# AUTHENTICATION & USER SCHEMAS
# ============================================================================


class PatientRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    phone: str = Field(..., min_length=7, max_length=35)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(default=None, max_length=25)
    address: Optional[str] = Field(default=None, max_length=500)
    verification_channel: str = Field(default="email", max_length=20)
    privacy_consent_accepted: bool = Field(...)

    @field_validator("privacy_consent_accepted")
    @classmethod
    def check_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must accept the Privacy Policy and consent terms to register.")
        return v


class SendOtpRequest(BaseModel):
    channel: str = Field(default="email", max_length=20)


class VerifyOtpRequest(BaseModel):
    otp_code: str = Field(..., min_length=4, max_length=12)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


class UserSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    phone: Optional[str] = None
    full_name: str
    role_name: str
    is_active: bool
    is_email_verified: bool
    redirect_url: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    csrf_token: str
    role: str
    redirect_url: str
    user: UserSummaryOut
    verification_info: Optional[Dict[str, Any]] = None


# ============================================================================
# PATIENT, DOCTOR & STAFF PROFILE SCHEMAS
# ============================================================================


class PatientProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    phone: Optional[str] = Field(default=None, min_length=7, max_length=35)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(default=None, max_length=25)
    blood_group: Optional[str] = Field(default=None, max_length=10)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=80)
    emergency_contact_name: Optional[str] = Field(default=None, max_length=150)
    emergency_contact_phone: Optional[str] = Field(default=None, max_length=35)


class AdminCreatePatientRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    email: Optional[EmailStr] = None
    phone: str = Field(..., min_length=7, max_length=35)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    address: Optional[str] = None
    city: str = "Lahore"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    primary_doctor_id: Optional[int] = None


class AdminCreateDoctorRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    phone: str = Field(..., min_length=7, max_length=35)
    password: str = Field(..., min_length=8, max_length=128)
    title: str = "Dental Surgeon"
    specialization: str = "General & Cosmetic Dentistry"
    qualification: Optional[str] = None
    license_number: Optional[str] = None
    bio: Optional[str] = None
    consultation_fee: Decimal = Decimal("1500.00")
    slot_duration_minutes: int = 30
    is_public: bool = True


class DoctorUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    specialization: Optional[str] = None
    qualification: Optional[str] = None
    license_number: Optional[str] = None
    bio: Optional[str] = None
    consultation_fee: Optional[Decimal] = None
    slot_duration_minutes: Optional[int] = None
    is_public: Optional[bool] = None
    is_active: Optional[bool] = None


class DoctorScheduleItemInput(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: str = "16:00"
    end_time: str = "22:00"
    break_start: Optional[str] = None
    break_end: Optional[str] = None
    slot_duration_minutes: int = 30
    is_available: bool = True


class AdminCreateStaffRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    phone: str = Field(..., min_length=7, max_length=35)
    password: str = Field(..., min_length=8, max_length=128)
    designation: str = "Clinic Administrator"
    department: str = "Administration"
    can_view_clinical_details: bool = False


# ============================================================================
# SERVICE & APPOINTMENT SCHEMAS
# ============================================================================


class ServiceCreateUpdate(BaseModel):
    code: str = Field(..., min_length=2, max_length=32)
    name: str = Field(..., min_length=2, max_length=150)
    category: str = Field(..., min_length=2, max_length=80)
    tagline: Optional[str] = None
    short_description: str = Field(..., min_length=5, max_length=500)
    detailed_description: Optional[str] = None
    price: Decimal = Field(..., ge=Decimal("0.00"))
    duration_minutes: int = Field(default=30, ge=10, le=240)
    icon_name: str = "stethoscope"
    is_published: bool = True
    is_bookable: bool = True
    display_order: int = 10


class ServiceUpdateRequest(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=32)
    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    category: Optional[str] = Field(default=None, min_length=2, max_length=80)
    tagline: Optional[str] = None
    short_description: Optional[str] = Field(default=None, min_length=5, max_length=500)
    detailed_description: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"))
    duration_minutes: Optional[int] = Field(default=None, ge=10, le=240)
    icon_name: Optional[str] = None
    is_published: Optional[bool] = None
    is_bookable: Optional[bool] = None
    display_order: Optional[int] = None


class AppointmentCreateRequest(BaseModel):
    patient_id: Optional[int] = None
    doctor_id: int
    service_id: Optional[int] = None
    appointment_date: date
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    reason_for_visit: str = Field(..., min_length=3, max_length=1000)
    patient_notes: Optional[str] = Field(default=None, max_length=1000)


class AppointmentStatusUpdateRequest(BaseModel):
    status: str
    cancellation_reason: Optional[str] = None
    clinical_status_notes: Optional[str] = None
    follow_up_recommended_date: Optional[date] = None


class AppointmentRescheduleRequest(BaseModel):
    appointment_date: date
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    doctor_id: Optional[int] = None
    reason: Optional[str] = None


# ============================================================================
# CLINICAL ENCOUNTER, MEDICAL HISTORY, DENTAL CHART, TREATMENT & RX SCHEMAS
# ============================================================================


class MedicalHistoryUpdateRequest(BaseModel):
    systemic_conditions: Optional[str] = None
    current_medications: Optional[str] = None
    previous_surgeries: Optional[str] = None
    bleeding_disorders: bool = False
    diabetes: bool = False
    hypertension: bool = False
    heart_condition: bool = False
    pregnancy_status: Optional[str] = None
    smoking_tobacco_use: Optional[str] = None
    dental_anxiety_level: Optional[str] = None
    previous_dental_history: Optional[str] = None
    last_dental_visit_date: Optional[date] = None
    notes: Optional[str] = None


class AllergyCreateRequest(BaseModel):
    allergen: str = Field(..., min_length=2, max_length=150)
    reaction: Optional[str] = None
    severity: str = "Moderate"


class ClinicalEncounterCreateRequest(BaseModel):
    patient_id: int
    appointment_id: Optional[int] = None
    visit_date: Optional[date] = None
    presenting_complaint: str = Field(..., min_length=2)
    history_of_present_illness: Optional[str] = None
    medical_history_summary: Optional[str] = None
    allergies_summary: Optional[str] = None
    examination_findings: Optional[str] = None
    extra_oral_findings: Optional[str] = None
    intra_oral_findings: Optional[str] = None
    tooth_specific_findings: Optional[str] = None
    diagnosis_summary: Optional[str] = None
    treatment_performed: Optional[str] = None
    treatment_plan_notes: Optional[str] = None
    follow_up_instructions: Optional[str] = None
    next_recommended_visit_date: Optional[date] = None
    finalize: bool = False


class ClinicalEncounterUpdateRequest(BaseModel):
    presenting_complaint: Optional[str] = None
    history_of_present_illness: Optional[str] = None
    medical_history_summary: Optional[str] = None
    allergies_summary: Optional[str] = None
    examination_findings: Optional[str] = None
    extra_oral_findings: Optional[str] = None
    intra_oral_findings: Optional[str] = None
    tooth_specific_findings: Optional[str] = None
    diagnosis_summary: Optional[str] = None
    treatment_performed: Optional[str] = None
    treatment_plan_notes: Optional[str] = None
    follow_up_instructions: Optional[str] = None
    next_recommended_visit_date: Optional[date] = None
    finalize: Optional[bool] = None
    amendment_reason: Optional[str] = None


class RecordCorrectionCreateRequest(BaseModel):
    encounter_id: Optional[int] = None
    section_name: str = Field(..., min_length=2, max_length=80)
    requested_change: str = Field(..., min_length=5, max_length=1500)


class ToothChartUpdateRequest(BaseModel):
    tooth_fdi: str = Field(..., min_length=2, max_length=5)
    condition_status: str = Field(..., min_length=2, max_length=40)
    surfaces: Optional[str] = None
    mobility_grade: Optional[str] = None
    clinical_notes: Optional[str] = None
    treatment_recommended: Optional[str] = None
    encounter_id: Optional[int] = None


class DiagnosisCreateRequest(BaseModel):
    patient_id: int
    encounter_id: Optional[int] = None
    tooth_fdi: Optional[str] = None
    diagnosis_code: Optional[str] = None
    diagnosis_title: str = Field(..., min_length=2, max_length=200)
    severity: str = "Moderate"
    clinical_notes: Optional[str] = None
    status: str = "Active"


class TreatmentPlanItemInput(BaseModel):
    service_id: Optional[int] = None
    tooth_fdi: Optional[str] = None
    procedure_name: str = Field(..., min_length=2, max_length=200)
    estimated_cost: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    priority: str = "Standard"
    scheduled_date: Optional[date] = None
    notes: Optional[str] = None


class TreatmentPlanCreateRequest(BaseModel):
    patient_id: int
    encounter_id: Optional[int] = None
    title: str = Field(..., min_length=2, max_length=200)
    clinical_summary: Optional[str] = None
    items: List[TreatmentPlanItemInput] = Field(default_factory=list)


class TreatmentRecordCreateRequest(BaseModel):
    patient_id: int
    appointment_id: Optional[int] = None
    encounter_id: Optional[int] = None
    treatment_plan_item_id: Optional[int] = None
    service_id: Optional[int] = None
    tooth_fdi: Optional[str] = None
    surface: Optional[str] = None
    procedure_name: str = Field(..., min_length=2, max_length=200)
    clinical_description: str = Field(..., min_length=2)
    materials_used: Optional[str] = None
    complications: Optional[str] = None
    post_op_instructions: Optional[str] = None
    follow_up_recommended: Optional[date] = None
    performed_date: Optional[date] = None


class PrescriptionItemInput(BaseModel):
    medication_name: str = Field(..., min_length=2, max_length=200)
    strength: Optional[str] = None
    dosage: str = Field(..., min_length=1, max_length=100)
    route: str = "Oral"
    frequency: str = Field(..., min_length=1, max_length=100)
    duration: str = Field(..., min_length=1, max_length=80)
    quantity: Optional[str] = None
    instructions: Optional[str] = None


class PrescriptionCreateRequest(BaseModel):
    patient_id: int
    encounter_id: Optional[int] = None
    appointment_id: Optional[int] = None
    diagnosis_notes: Optional[str] = None
    general_instructions: Optional[str] = None
    items: List[PrescriptionItemInput] = Field(..., min_length=1)


# ============================================================================
# BILLING, INVOICE, PAYMENT, RECEIPT & REVIEW SCHEMAS
# ============================================================================


class InvoiceLineItemInput(BaseModel):
    service_id: Optional[int] = None
    tooth_fdi: Optional[str] = None
    description: str = Field(..., min_length=2, max_length=255)
    quantity: int = Field(default=1, ge=1, le=100)
    unit_price: Decimal = Field(..., ge=Decimal("0.00"))


class InvoiceCreateRequest(BaseModel):
    patient_id: int
    appointment_id: Optional[int] = None
    encounter_id: Optional[int] = None
    document_kind: str = "Invoice"  # Invoice or Estimate
    due_date: Optional[date] = None
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    discount_reason: Optional[str] = None
    tax_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    notes: Optional[str] = None
    items: List[InvoiceLineItemInput] = Field(..., min_length=1)


class PaymentRecordRequest(BaseModel):
    invoice_id: int
    amount: Decimal = Field(..., gt=Decimal("0.00"))
    payment_method: str = "Cash"
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class PaymentReverseRequest(BaseModel):
    reversal_reason: str = Field(..., min_length=3, max_length=500)


class ReviewSubmitRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = Field(default=None, max_length=150)
    comment: str = Field(..., min_length=5, max_length=1500)
    reviewer_display_name: Optional[str] = Field(default=None, max_length=120)
    consent_to_publish: bool = True


class ReviewModerationRequest(BaseModel):
    status: str = Field(..., pattern=r"^(Approved|Rejected|Hidden|Pending)$")
    moderation_reason: Optional[str] = None


class ClinicSettingsUpdateRequest(BaseModel):
    clinic_name: Optional[str] = None
    tagline: Optional[str] = None
    hero_subtitle: Optional[str] = None
    lead_dentist_name: Optional[str] = None
    about_summary: Optional[str] = None
    phone_primary: Optional[str] = None
    whatsapp_number: Optional[str] = None
    email_contact: Optional[str] = None
    address_line: Optional[str] = None
    city: Optional[str] = None
    google_maps_url: Optional[str] = None
    facebook_url: Optional[str] = None
    opening_hours_days: Optional[str] = None
    opening_hours_time: Optional[str] = None
    opening_time_24h: Optional[str] = None
    closing_time_24h: Optional[str] = None
    currency: Optional[str] = None
    appointment_slot_minutes: Optional[int] = None
    cancellation_notice_hours: Optional[int] = None
