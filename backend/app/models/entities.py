from datetime import date, datetime, time
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utcnow


# ============================================================================
# 1 & 2. ROLES, PERMISSIONS & USERS
# ============================================================================


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    users: Mapped[List["User"]] = relationship("User", back_populates="role")
    role_permissions: Mapped[List["RolePermission"]] = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    role_permissions: Mapped[List["RolePermission"]] = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    role: Mapped["Role"] = relationship("Role", back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="role_permissions")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(35), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="joined")
    patient_profile: Mapped[Optional["PatientProfile"]] = relationship(
        "PatientProfile", back_populates="user", uselist=False, foreign_keys="PatientProfile.user_id"
    )
    doctor_profile: Mapped[Optional["DoctorProfile"]] = relationship(
        "DoctorProfile", back_populates="user", uselist=False
    )
    staff_profile: Mapped[Optional["StaffProfile"]] = relationship(
        "StaffProfile", back_populates="user", uselist=False
    )


# ============================================================================
# 3, 4, 5. PATIENT, DOCTOR & STAFF PROFILES
# ============================================================================


class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True, index=True
    )
    patient_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str] = mapped_column(String(35), nullable=False, index=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(25), nullable=True)
    blood_group: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[str] = mapped_column(String(80), default="Lahore", nullable=False)
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(35), nullable=True)

    # Support guardian relationship without automatic cross-account access
    guardian_patient_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="SET NULL"), nullable=True
    )
    primary_doctor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    branch_code: Mapped[str] = mapped_column(String(30), default="JOHAR-TOWN-MAIN", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    archived_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="patient_profile", foreign_keys=[user_id]
    )
    primary_doctor: Mapped[Optional["DoctorProfile"]] = relationship("DoctorProfile")
    medical_history: Mapped[Optional["MedicalHistory"]] = relationship(
        "MedicalHistory", back_populates="patient", uselist=False
    )
    allergies: Mapped[List["Allergy"]] = relationship("Allergy", back_populates="patient")
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="patient")
    encounters: Mapped[List["ClinicalEncounter"]] = relationship("ClinicalEncounter", back_populates="patient")
    dental_chart_teeth: Mapped[List["DentalChartTooth"]] = relationship(
        "DentalChartTooth", back_populates="patient"
    )
    treatment_plans: Mapped[List["TreatmentPlan"]] = relationship("TreatmentPlan", back_populates="patient")
    treatment_records: Mapped[List["TreatmentRecord"]] = relationship(
        "TreatmentRecord", back_populates="patient"
    )
    prescriptions: Mapped[List["Prescription"]] = relationship("Prescription", back_populates="patient")
    documents: Mapped[List["ClinicalDocument"]] = relationship("ClinicalDocument", back_populates="patient")
    invoices: Mapped[List["Invoice"]] = relationship("Invoice", back_populates="patient")


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False, index=True
    )
    doctor_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(80), default="Dental Surgeon", nullable=False)
    specialization: Mapped[str] = mapped_column(String(150), default="General & Cosmetic Dentistry", nullable=False)
    qualification: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    license_number: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consultation_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("1500.00"), nullable=False)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    branch_code: Mapped[str] = mapped_column(String(30), default="JOHAR-TOWN-MAIN", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="doctor_profile")
    schedules: Mapped[List["DoctorSchedule"]] = relationship(
        "DoctorSchedule", back_populates="doctor", cascade="all, delete-orphan"
    )
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="doctor")


class StaffProfile(Base):
    __tablename__ = "staff_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False, index=True
    )
    staff_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    designation: Mapped[str] = mapped_column(String(100), default="Clinic Administrator", nullable=False)
    department: Mapped[str] = mapped_column(String(100), default="Administration", nullable=False)
    can_view_clinical_details: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    branch_code: Mapped[str] = mapped_column(String(30), default="JOHAR-TOWN-MAIN", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="staff_profile")


# ============================================================================
# 6, 7, 8. DOCTOR SCHEDULES, SERVICES & APPOINTMENTS
# ============================================================================


class DoctorSchedule(Base):
    __tablename__ = "doctor_schedules"
    __table_args__ = (UniqueConstraint("doctor_id", "day_of_week", name="uq_doctor_day_schedule"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 0 = Monday ... 5 = Saturday, 6 = Sunday
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, default=time(16, 0), nullable=False)
    end_time: Mapped[time] = mapped_column(Time, default=time(22, 0), nullable=False)
    break_start: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    break_end: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    doctor: Mapped["DoctorProfile"] = relationship("DoctorProfile", back_populates="schedules")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    tagline: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    short_description: Mapped[str] = mapped_column(String(500), nullable=False)
    detailed_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    icon_name: Mapped[str] = mapped_column(String(60), default="stethoscope", nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_bookable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointment_doctor_date_time", "doctor_id", "appointment_date", "start_time"),
        Index("ix_appointment_patient_date", "patient_id", "appointment_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appointment_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    service_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True, index=True
    )
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    # Statuses: Requested, Confirmed, CheckedIn, InProgress, Completed, Cancelled, NoShow
    status: Mapped[str] = mapped_column(String(30), default="Requested", nullable=False, index=True)
    reason_for_visit: Mapped[str] = mapped_column(Text, nullable=False)
    patient_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    clinical_status_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    rescheduled_from_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    checked_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_recommended_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    patient: Mapped["PatientProfile"] = relationship("PatientProfile", back_populates="appointments")
    doctor: Mapped["DoctorProfile"] = relationship("DoctorProfile", back_populates="appointments")
    service: Mapped[Optional["Service"]] = relationship("Service")
    encounter: Mapped[Optional["ClinicalEncounter"]] = relationship(
        "ClinicalEncounter", back_populates="appointment", uselist=False
    )


# ============================================================================
# 9, 10, 11. CLINICAL ENCOUNTERS, AMENDMENTS, MEDICAL HISTORY & ALLERGIES
# ============================================================================


class ClinicalEncounter(Base):
    __tablename__ = "clinical_encounters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    encounter_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    appointment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), unique=True, nullable=True, index=True
    )
    visit_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False, index=True)

    presenting_complaint: Mapped[str] = mapped_column(Text, nullable=False)
    history_of_present_illness: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    medical_history_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allergies_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    examination_findings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_oral_findings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intra_oral_findings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tooth_specific_findings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diagnosis_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    treatment_performed: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    treatment_plan_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    follow_up_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_recommended_visit_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Draft, Finalized, Amended
    status: Mapped[str] = mapped_column(String(25), default="Draft", nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    patient: Mapped["PatientProfile"] = relationship("PatientProfile", back_populates="encounters")
    doctor: Mapped["DoctorProfile"] = relationship("DoctorProfile")
    appointment: Mapped[Optional["Appointment"]] = relationship("Appointment", back_populates="encounter")
    amendments: Mapped[List["EncounterAmendment"]] = relationship(
        "EncounterAmendment", back_populates="encounter", cascade="all, delete-orphan"
    )
    diagnoses: Mapped[List["Diagnosis"]] = relationship(
        "Diagnosis", back_populates="encounter", cascade="all, delete-orphan"
    )


class EncounterAmendment(Base):
    __tablename__ = "encounter_amendments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    amendment_reason: Mapped[str] = mapped_column(Text, nullable=False)
    previous_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    amended_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    encounter: Mapped["ClinicalEncounter"] = relationship("ClinicalEncounter", back_populates="amendments")


class RecordCorrectionRequest(Base):
    """Allows patients to request corrections to clinical/historical records without editing clinical data directly."""
    __tablename__ = "record_correction_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    encounter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="SET NULL"), nullable=True
    )
    section_name: Mapped[str] = mapped_column(String(80), nullable=False)
    requested_change: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(25), default="Pending", nullable=False, index=True)
    staff_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MedicalHistory(Base):
    __tablename__ = "medical_histories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    systemic_conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_medications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    previous_surgeries: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bleeding_disorders: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    diabetes: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hypertension: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    heart_condition: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pregnancy_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    smoking_tobacco_use: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    dental_anxiety_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    previous_dental_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_dental_visit_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    patient: Mapped["PatientProfile"] = relationship("PatientProfile", back_populates="medical_history")


class Allergy(Base):
    __tablename__ = "allergies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    allergen: Mapped[str] = mapped_column(String(150), nullable=False)
    reaction: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    severity: Mapped[str] = mapped_column(String(30), default="Moderate", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recorded_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    patient: Mapped["PatientProfile"] = relationship("PatientProfile", back_populates="allergies")


# ============================================================================
# 12, 13, 14, 15. DENTAL CHARTS (FDI), DIAGNOSES, TREATMENT PLANS & RECORDS
# ============================================================================


class DentalChartTooth(Base):
    __tablename__ = "dental_chart_teeth"
    __table_args__ = (UniqueConstraint("patient_id", "tooth_fdi", name="uq_patient_tooth_fdi"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # FDI notation: Permanent 11-18, 21-28, 31-38, 41-48; Primary 51-55, 61-65, 71-75, 81-85
    tooth_fdi: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    dentition_type: Mapped[str] = mapped_column(String(20), default="Permanent", nullable=False)
    tooth_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Sound, Caries, Filled, Crown, RootCanalTreated, Missing, ExtractionIndicated, Implant, BridgePontic, Fractured, Sealant
    condition_status: Mapped[str] = mapped_column(String(40), default="Sound", nullable=False)
    surfaces: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    mobility_grade: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    clinical_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by_doctor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    patient: Mapped["PatientProfile"] = relationship("PatientProfile", back_populates="dental_chart_teeth")
    findings_history: Mapped[List["ToothFinding"]] = relationship(
        "ToothFinding", back_populates="chart_tooth", cascade="all, delete-orphan"
    )


class ToothFinding(Base):
    __tablename__ = "tooth_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chart_tooth_id: Mapped[int] = mapped_column(
        ForeignKey("dental_chart_teeth.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    encounter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="SET NULL"), nullable=True
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    tooth_fdi: Mapped[str] = mapped_column(String(10), nullable=False)
    condition_status: Mapped[str] = mapped_column(String(40), nullable=False)
    surfaces: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    finding_notes: Mapped[str] = mapped_column(Text, nullable=False)
    treatment_recommended: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    chart_tooth: Mapped["DentalChartTooth"] = relationship("DentalChartTooth", back_populates="findings_history")


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    encounter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="CASCADE"), nullable=True, index=True
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tooth_fdi: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    diagnosis_code: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    diagnosis_title: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), default="Moderate", nullable=False)
    clinical_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Active", nullable=False)
    diagnosed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    encounter: Mapped[Optional["ClinicalEncounter"]] = relationship("ClinicalEncounter", back_populates="diagnoses")


class TreatmentPlan(Base):
    __tablename__ = "treatment_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    encounter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    clinical_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Proposed", nullable=False, index=True)
    total_estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    patient: Mapped["PatientProfile"] = relationship("PatientProfile", back_populates="treatment_plans")
    doctor: Mapped["DoctorProfile"] = relationship("DoctorProfile")
    items: Mapped[List["TreatmentPlanItem"]] = relationship(
        "TreatmentPlanItem", back_populates="treatment_plan", cascade="all, delete-orphan"
    )


class TreatmentPlanItem(Base):
    __tablename__ = "treatment_plan_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    treatment_plan_id: Mapped[int] = mapped_column(
        ForeignKey("treatment_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )
    tooth_fdi: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    procedure_name: Mapped[str] = mapped_column(String(200), nullable=False)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    priority: Mapped[str] = mapped_column(String(30), default="Standard", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="Planned", nullable=False)
    scheduled_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    treatment_plan: Mapped["TreatmentPlan"] = relationship("TreatmentPlan", back_populates="items")


class TreatmentRecord(Base):
    __tablename__ = "treatment_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    appointment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    encounter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="SET NULL"), nullable=True
    )
    treatment_plan_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("treatment_plan_items.id", ondelete="SET NULL"), nullable=True
    )
    service_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )
    tooth_fdi: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    surface: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    procedure_name: Mapped[str] = mapped_column(String(200), nullable=False)
    clinical_description: Mapped[str] = mapped_column(Text, nullable=False)
    materials_used: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    complications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    post_op_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    follow_up_recommended: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    performed_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    patient: Mapped["PatientProfile"] = relationship("PatientProfile", back_populates="treatment_records")
    doctor: Mapped["DoctorProfile"] = relationship("DoctorProfile")


# ============================================================================
# 16, 17, 18. PRESCRIPTIONS & CLINICAL DOCUMENTS / X-RAYS
# ============================================================================


class Prescription(Base):
    __tablename__ = "prescriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prescription_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    encounter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="SET NULL"), nullable=True
    )
    appointment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    issue_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False, index=True)
    diagnosis_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    general_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    patient: Mapped["PatientProfile"] = relationship("PatientProfile", back_populates="prescriptions")
    doctor: Mapped["DoctorProfile"] = relationship("DoctorProfile")
    items: Mapped[List["PrescriptionItem"]] = relationship(
        "PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan"
    )


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prescription_id: Mapped[int] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    medication_name: Mapped[str] = mapped_column(String(200), nullable=False)
    strength: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    dosage: Mapped[str] = mapped_column(String(100), nullable=False)
    route: Mapped[str] = mapped_column(String(60), default="Oral", nullable=False)
    frequency: Mapped[str] = mapped_column(String(100), nullable=False)
    duration: Mapped[str] = mapped_column(String(80), nullable=False)
    quantity: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    prescription: Mapped["Prescription"] = relationship("Prescription", back_populates="items")


class ClinicalDocument(Base):
    __tablename__ = "clinical_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    appointment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    encounter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="SET NULL"), nullable=True
    )
    treatment_record_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("treatment_records.id", ondelete="SET NULL"), nullable=True
    )
    tooth_fdi: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # X-Ray, OPG, Bitewing, Periapical, CBCT/DICOM, LabReport, ClinicalPhoto, ConsentForm, Other
    document_type: Mapped[str] = mapped_column(String(50), default="X-Ray", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    clinical_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    is_patient_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    patient: Mapped["PatientProfile"] = relationship("PatientProfile", back_populates="documents")
    uploaded_by: Mapped["User"] = relationship("User")


# ============================================================================
# 19, 20, 21, 22. INVOICES, LINE ITEMS, PAYMENTS & RECEIPTS (DECIMAL PKR)
# ============================================================================


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    appointment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    encounter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="SET NULL"), nullable=True
    )
    # Invoice or Estimate
    document_kind: Mapped[str] = mapped_column(String(20), default="Invoice", nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False, index=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="PKR", nullable=False)

    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    discount_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    balance_due: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)

    # Unpaid, PartiallyPaid, Paid, Voided, Estimate
    status: Mapped[str] = mapped_column(String(30), default="Unpaid", nullable=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    patient: Mapped["PatientProfile"] = relationship("PatientProfile", back_populates="invoices")
    line_items: Mapped[List["InvoiceLineItem"]] = relationship(
        "InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan"
    )
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="invoice")
    receipts: Mapped[List["Receipt"]] = relationship("Receipt", back_populates="invoice")


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )
    tooth_fdi: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="line_items")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="PKR", nullable=False)
    payment_method: Mapped[str] = mapped_column(String(40), default="Cash", nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Recorded, Reversed
    status: Mapped[str] = mapped_column(String(25), default="Recorded", nullable=False, index=True)
    reversal_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reversed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    received_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    payment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="payments")
    patient: Mapped["PatientProfile"] = relationship("PatientProfile")
    receipt: Mapped[Optional["Receipt"]] = relationship("Receipt", back_populates="payment", uselist=False)


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    receipt_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    # Strictly linked 1-to-1 with an actual recorded Payment
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), unique=True, nullable=False, index=True
    )
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount_received: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="PKR", nullable=False)
    payment_method: Mapped[str] = mapped_column(String(40), nullable=False)
    issued_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    is_voided: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    payment: Mapped["Payment"] = relationship("Payment", back_populates="receipt")
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="receipts")
    patient: Mapped["PatientProfile"] = relationship("PatientProfile")


# ============================================================================
# 23, 24, 25, 26, 27. REVIEWS, NOTIFICATIONS, AUDIT LOGS, RESET TOKENS, CONSENT & SETTINGS
# ============================================================================


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating_range"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewer_display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    # Pending, Approved, Rejected, Hidden
    status: Mapped[str] = mapped_column(String(25), default="Pending", nullable=False, index=True)
    consent_to_publish: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deletion_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    moderation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    moderated_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    moderated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_label: Mapped[str] = mapped_column(String(60), default="Verified Patient", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(40), default="System", nullable=False, index=True)
    related_entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    related_entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), default="InApp", nullable=False)
    external_delivery_status: Mapped[str] = mapped_column(
        String(40), default="InAppDelivered", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    consent_type: Mapped[str] = mapped_column(String(60), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(30), default="v1.0", nullable=False)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClinicSetting(Base):
    __tablename__ = "clinic_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clinic_name: Mapped[str] = mapped_column(String(150), default="Rumi Dental Care", nullable=False)
    tagline: Mapped[str] = mapped_column(
        String(255), default="Smile Bright, Live Brighter — Your Dental Care Destination", nullable=False
    )
    hero_subtitle: Mapped[str] = mapped_column(
        String(255), default="Your Oral Health Matters to Us", nullable=False
    )
    lead_dentist_name: Mapped[str] = mapped_column(String(150), default="Dr. Aisha Salman", nullable=False)
    about_summary: Mapped[str] = mapped_column(
        Text,
        default=(
            "At our dental clinic, we are dedicated to providing top-quality dental care & maintaining optimal oral "
            "health for our patients. Our team of highly skilled & experienced dentists are committed to delivering "
            "personalized & comprehensive dental services. Our clinic is equipped with state-of-the-art technology & "
            "modern dental equipment, allowing us to offer a wide range of services."
        ),
        nullable=False,
    )
    phone_primary: Mapped[str] = mapped_column(String(40), default="+92 310 2468080", nullable=False)
    whatsapp_number: Mapped[str] = mapped_column(String(40), default="+92 310 2468080", nullable=False)
    email_contact: Mapped[str] = mapped_column(String(150), default="info@rumidentalcare.com", nullable=False)
    address_line: Mapped[str] = mapped_column(
        String(255), default="388 A, Block A, RECHS, Johar Town, Lahore", nullable=False
    )
    city: Mapped[str] = mapped_column(String(80), default="Lahore", nullable=False)
    country: Mapped[str] = mapped_column(String(80), default="Pakistan", nullable=False)
    google_maps_url: Mapped[str] = mapped_column(
        Text,
        default="https://www.google.com/maps/place/Rumi+Dental+Care/@31.4524517,74.2803009,17z/data=!3m1!4b1!4m6!3m5!1s0x3919019271aac90f:0xee24db7d2bf73975!8m2!3d31.4524471!4d74.2828758!16s%2Fg%2F11jzb3qkw9",
        nullable=False,
    )
    facebook_url: Mapped[str] = mapped_column(
        String(255), default="https://www.facebook.com/RumiDentalCare", nullable=False
    )
    opening_hours_days: Mapped[str] = mapped_column(String(80), default="Mon-Sat", nullable=False)
    opening_hours_time: Mapped[str] = mapped_column(String(80), default="04:00 PM – 10:00 PM", nullable=False)
    opening_time_24h: Mapped[str] = mapped_column(String(10), default="16:00", nullable=False)
    closing_time_24h: Mapped[str] = mapped_column(String(10), default="22:00", nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="PKR", nullable=False)
    appointment_slot_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    cancellation_notice_hours: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
