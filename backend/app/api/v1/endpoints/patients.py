from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.permissions import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import hash_password, log_audit_event, validate_password_strength
from app.db.session import get_db
from app.dependencies.auth import (
    get_current_patient_profile,
    get_current_user,
    require_roles,
    verify_patient_isolation,
)
from app.models.entities import (
    Allergy,
    Appointment,
    ClinicalDocument,
    ClinicalEncounter,
    ClinicSetting,
    ConsentRecord,
    DentalChartTooth,
    Diagnosis,
    EncounterAmendment,
    Invoice,
    InvoiceLineItem,
    MedicalHistory,
    Notification,
    PasswordResetToken,
    PatientProfile,
    Payment,
    Prescription,
    PrescriptionItem,
    Receipt,
    RecordCorrectionRequest,
    Review,
    Role,
    ToothFinding,
    TreatmentPlan,
    TreatmentPlanItem,
    TreatmentRecord,
    User,
)
from app.schemas.domain import (
    AdminCreatePatientRequest,
    AllergyCreateRequest,
    MedicalHistoryUpdateRequest,
    PatientProfileUpdate,
    RecordCorrectionCreateRequest,
)
from app.services.pdf_service import generate_treatment_summary_pdf


router = APIRouter()


def _serialize_patient(p: PatientProfile, include_clinical_counts: bool = False) -> dict:
    data = {
        "id": p.id,
        "user_id": p.user_id,
        "patient_number": p.patient_number,
        "full_name": p.full_name,
        "email": p.email,
        "phone": p.phone,
        "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
        "gender": p.gender,
        "blood_group": p.blood_group,
        "address": p.address,
        "city": p.city,
        "emergency_contact_name": p.emergency_contact_name,
        "emergency_contact_phone": p.emergency_contact_phone,
        "primary_doctor_id": p.primary_doctor_id,
        "primary_doctor_name": p.primary_doctor.full_name if p.primary_doctor else None,
        "branch_code": p.branch_code,
        "is_active": p.is_active,
        "is_archived": p.is_archived,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
    if include_clinical_counts:
        outstanding = sum((inv.balance_due for inv in p.invoices if inv.status != "Voided"), Decimal("0.00"))
        data["appointments_count"] = len(p.appointments)
        data["outstanding_balance"] = float(outstanding)
    return data


@router.get("/me")
def get_my_patient_profile(
    patient: PatientProfile = Depends(get_current_patient_profile),
):
    return _serialize_patient(patient, include_clinical_counts=True)


@router.put("/me")
def update_my_patient_profile(
    payload: PatientProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_PATIENT)),
    patient: PatientProfile = Depends(get_current_patient_profile),
):
    update_fields = payload.model_dump(exclude_unset=True)
    for k, v in update_fields.items():
        setattr(patient, k, v)
    if "full_name" in update_fields and update_fields["full_name"]:
        current_user.full_name = update_fields["full_name"]
    if "phone" in update_fields and update_fields["phone"]:
        current_user.phone = update_fields["phone"]

    log_audit_event(
        db=db,
        action="PATIENT_UPDATED_OWN_PROFILE",
        resource_type="patient_profile",
        actor=current_user,
        resource_id=patient.id,
        patient_id=patient.id,
        request=request,
    )
    db.commit()
    db.refresh(patient)
    return _serialize_patient(patient)


@router.get("/me/dashboard")
def get_my_patient_dashboard(
    db: Session = Depends(get_db),
    patient: PatientProfile = Depends(get_current_patient_profile),
):
    today = date.today()
    upcoming_apts = (
        db.query(Appointment)
        .filter(
            Appointment.patient_id == patient.id,
            Appointment.appointment_date >= today,
            Appointment.status.in_(["Requested", "Confirmed", "CheckedIn", "InProgress"]),
        )
        .order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
        .all()
    )
    previous_visits = (
        db.query(Appointment)
        .filter(
            Appointment.patient_id == patient.id,
            or_(Appointment.appointment_date < today, Appointment.status == "Completed"),
        )
        .order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc())
        .limit(10)
        .all()
    )
    recent_treatments = (
        db.query(TreatmentRecord)
        .filter(TreatmentRecord.patient_id == patient.id)
        .order_by(TreatmentRecord.performed_date.desc())
        .limit(10)
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
        .limit(10)
        .all()
    )
    documents = (
        db.query(ClinicalDocument)
        .filter(ClinicalDocument.patient_id == patient.id, ClinicalDocument.is_patient_visible.is_(True))
        .order_by(ClinicalDocument.created_at.desc())
        .limit(10)
        .all()
    )
    encounters = (
        db.query(ClinicalEncounter)
        .filter(ClinicalEncounter.patient_id == patient.id)
        .order_by(ClinicalEncounter.visit_date.desc())
        .limit(5)
        .all()
    )

    outstanding_balance = sum(
        (inv.balance_due for inv in invoices if inv.document_kind == "Invoice"), Decimal("0.00")
    )
    follow_ups = [
        {
            "encounter_number": e.encounter_number,
            "recommended_date": e.next_recommended_visit_date.isoformat(),
            "instructions": e.follow_up_instructions,
        }
        for e in encounters
        if e.next_recommended_visit_date
    ]

    return {
        "patient": _serialize_patient(patient),
        "upcoming_appointment": (
            {
                "id": upcoming_apts[0].id,
                "appointment_number": upcoming_apts[0].appointment_number,
                "appointment_date": upcoming_apts[0].appointment_date.isoformat(),
                "start_time": upcoming_apts[0].start_time.strftime("%H:%M"),
                "status": upcoming_apts[0].status,
                "doctor_name": upcoming_apts[0].doctor.full_name if upcoming_apts[0].doctor else "Dr. Aisha Salman",
                "service_name": upcoming_apts[0].service.name if upcoming_apts[0].service else "Dental Consultation",
                "reason_for_visit": upcoming_apts[0].reason_for_visit,
            }
            if upcoming_apts
            else None
        ),
        "upcoming_appointments_count": len(upcoming_apts),
        "previous_visits_count": len(previous_visits),
        "recent_treatments_count": len(recent_treatments),
        "outstanding_balance": float(outstanding_balance),
        "currency": "PKR",
        "recent_invoices": [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "issue_date": inv.issue_date.isoformat(),
                "total_amount": float(inv.total_amount),
                "amount_paid": float(inv.amount_paid),
                "balance_due": float(inv.balance_due),
                "status": inv.status,
            }
            for inv in invoices[:5]
        ],
        "recent_receipts": [
            {
                "id": r.id,
                "receipt_number": r.receipt_number,
                "amount_received": float(r.amount_received),
                "payment_method": r.payment_method,
                "issued_at": r.issued_at.isoformat(),
            }
            for r in receipts
        ],
        "recent_documents": [
            {
                "id": d.id,
                "document_uid": d.document_uid,
                "document_type": d.document_type,
                "title": d.title,
                "tooth_fdi": d.tooth_fdi,
                "created_at": d.created_at.isoformat(),
            }
            for d in documents
        ],
        "follow_up_reminders": follow_ups,
    }


@router.post("/me/correction-requests", status_code=status.HTTP_201_CREATED)
def submit_record_correction_request(
    payload: RecordCorrectionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_PATIENT)),
    patient: PatientProfile = Depends(get_current_patient_profile),
):
    req = RecordCorrectionRequest(
        patient_id=patient.id,
        encounter_id=payload.encounter_id,
        section_name=payload.section_name,
        requested_change=payload.requested_change,
        status="Pending",
    )
    db.add(req)
    log_audit_event(
        db=db,
        action="PATIENT_SUBMITTED_CORRECTION_REQUEST",
        resource_type="record_correction_request",
        actor=current_user,
        patient_id=patient.id,
        request=request,
        details={"section_name": payload.section_name},
    )
    db.commit()
    db.refresh(req)
    return {
        "id": req.id,
        "patient_id": req.patient_id,
        "section_name": req.section_name,
        "requested_change": req.requested_change,
        "status": req.status,
        "created_at": req.created_at.isoformat(),
    }


@router.get("")
def list_patients(
    q: Optional[str] = Query(default=None, description="Search by name, patient number, email, or phone"),
    city: Optional[str] = Query(default=None),
    include_archived: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR, ROLE_ADMIN)),
):
    query = db.query(PatientProfile)
    if not include_archived:
        query = query.filter(PatientProfile.is_archived.is_(False))
    if city:
        query = query.filter(func.lower(PatientProfile.city) == city.strip().lower())
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                PatientProfile.full_name.ilike(term),
                PatientProfile.patient_number.ilike(term),
                PatientProfile.email.ilike(term),
                PatientProfile.phone.ilike(term),
            )
        )
    total = query.count()
    items = (
        query.order_by(PatientProfile.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_serialize_patient(p, include_clinical_counts=True) for p in items],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def admin_create_patient(
    payload: AdminCreatePatientRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_DOCTOR)),
):
    user_id = None
    if payload.email:
        email_norm = payload.email.strip().lower()
        existing = db.query(User).filter(User.email == email_norm).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user account with this email already exists.",
            )
        if payload.password:
            err = validate_password_strength(payload.password)
            if err:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
            pwd_hash = hash_password(payload.password)
        else:
            pwd_hash = hash_password("Patient@Rumi2026!")

        patient_role = db.query(Role).filter(Role.name == ROLE_PATIENT).first()
        new_user = User(
            email=email_norm,
            phone=payload.phone.strip(),
            full_name=payload.full_name.strip(),
            password_hash=pwd_hash,
            role_id=patient_role.id,
            is_active=True,
        )
        db.add(new_user)
        db.flush()
        user_id = new_user.id

    year = datetime.now(timezone.utc).year
    next_seq = db.query(PatientProfile).count() + 1
    patient_number = f"RDC-{year}-{next_seq:05d}"
    while db.query(PatientProfile).filter(PatientProfile.patient_number == patient_number).first():
        next_seq += 1
        patient_number = f"RDC-{year}-{next_seq:05d}"

    profile = PatientProfile(
        user_id=user_id,
        patient_number=patient_number,
        full_name=payload.full_name.strip(),
        email=payload.email.strip().lower() if payload.email else None,
        phone=payload.phone.strip(),
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        blood_group=payload.blood_group,
        address=payload.address,
        city=payload.city,
        emergency_contact_name=payload.emergency_contact_name,
        emergency_contact_phone=payload.emergency_contact_phone,
        primary_doctor_id=payload.primary_doctor_id,
        is_active=True,
    )
    db.add(profile)
    db.flush()

    db.add(MedicalHistory(patient_id=profile.id, updated_by_id=current_user.id))
    log_audit_event(
        db=db,
        action="STAFF_CREATED_PATIENT",
        resource_type="patient_profile",
        actor=current_user,
        resource_id=profile.id,
        patient_id=profile.id,
        request=request,
        details={"patient_number": patient_number},
    )
    db.commit()
    db.refresh(profile)
    return _serialize_patient(profile)


@router.get("/{patient_id}")
def get_patient_by_id(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = verify_patient_isolation(db, current_user, patient_id, request, "patient_profile")
    log_audit_event(
        db=db,
        action="PATIENT_RECORD_VIEWED",
        resource_type="patient_profile",
        actor=current_user,
        resource_id=patient.id,
        patient_id=patient.id,
        request=request,
    )
    db.commit()

    med = patient.medical_history
    return {
        **_serialize_patient(patient, include_clinical_counts=True),
        "medical_history": (
            {
                "systemic_conditions": med.systemic_conditions,
                "current_medications": med.current_medications,
                "previous_surgeries": med.previous_surgeries,
                "bleeding_disorders": med.bleeding_disorders,
                "diabetes": med.diabetes,
                "hypertension": med.hypertension,
                "heart_condition": med.heart_condition,
                "pregnancy_status": med.pregnancy_status,
                "smoking_tobacco_use": med.smoking_tobacco_use,
                "dental_anxiety_level": med.dental_anxiety_level,
                "previous_dental_history": med.previous_dental_history,
                "last_dental_visit_date": med.last_dental_visit_date.isoformat()
                if med.last_dental_visit_date
                else None,
                "notes": med.notes,
            }
            if med
            else None
        ),
        "allergies": [
            {
                "id": a.id,
                "allergen": a.allergen,
                "reaction": a.reaction,
                "severity": a.severity,
                "is_active": a.is_active,
            }
            for a in patient.allergies
            if a.is_active
        ],
    }


@router.put("/{patient_id}/medical-history")
def update_patient_medical_history(
    patient_id: int,
    payload: MedicalHistoryUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR, ROLE_ADMIN)),
):
    patient = verify_patient_isolation(db, current_user, patient_id, request, "medical_history")
    med = db.query(MedicalHistory).filter(MedicalHistory.patient_id == patient.id).first()
    if not med:
        med = MedicalHistory(patient_id=patient.id)
        db.add(med)
        db.flush()

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(med, k, v)
    med.updated_by_id = current_user.id

    log_audit_event(
        db=db,
        action="MEDICAL_HISTORY_UPDATED",
        resource_type="medical_history",
        actor=current_user,
        resource_id=med.id,
        patient_id=patient.id,
        request=request,
    )
    db.commit()
    return {"message": "Medical history updated successfully.", "patient_id": patient.id}


@router.post("/{patient_id}/allergies", status_code=status.HTTP_201_CREATED)
def add_patient_allergy(
    patient_id: int,
    payload: AllergyCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR, ROLE_ADMIN)),
):
    patient = verify_patient_isolation(db, current_user, patient_id, request, "allergy")
    allergy = Allergy(
        patient_id=patient.id,
        allergen=payload.allergen.strip(),
        reaction=payload.reaction,
        severity=payload.severity,
        is_active=True,
        recorded_by_id=current_user.id,
    )
    db.add(allergy)
    log_audit_event(
        db=db,
        action="ALLERGY_RECORDED",
        resource_type="allergy",
        actor=current_user,
        patient_id=patient.id,
        request=request,
        details={"allergen": allergy.allergen, "severity": allergy.severity},
    )
    db.commit()
    db.refresh(allergy)
    return {
        "id": allergy.id,
        "allergen": allergy.allergen,
        "reaction": allergy.reaction,
        "severity": allergy.severity,
    }


@router.get("/{patient_id}/treatment-summary.pdf")
def download_patient_treatment_summary_pdf(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = verify_patient_isolation(db, current_user, patient_id, request, "treatment_summary_pdf")
    clinic = db.query(ClinicSetting).first() or ClinicSetting()
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

    pdf_bytes = generate_treatment_summary_pdf(patient, encounters, treatments, plans, clinic)
    log_audit_event(
        db=db,
        action="TREATMENT_SUMMARY_PDF_DOWNLOADED",
        resource_type="patient_profile",
        actor=current_user,
        resource_id=patient.id,
        patient_id=patient.id,
        request=request,
    )
    db.commit()

    filename = f"RumiDentalCare_Summary_{patient.patient_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.delete("/{patient_id}")
def admin_delete_patient(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """
    Allows an Administrator to permanently delete a patient profile and associated patient records.
    """
    patient = db.query(PatientProfile).filter(PatientProfile.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    patient_number = patient.patient_number
    patient_name = patient.full_name
    linked_user_id = patient.user_id

    # Clear guardian self-references pointing to this patient
    db.query(PatientProfile).filter(PatientProfile.guardian_patient_id == patient.id).update(
        {"guardian_patient_id": None}, synchronize_session=False
    )

    # 1. Financial records (Receipts -> Payments -> InvoiceLineItems -> Invoices)
    db.query(Receipt).filter(Receipt.patient_id == patient.id).delete(synchronize_session=False)
    db.query(Payment).filter(Payment.patient_id == patient.id).delete(synchronize_session=False)
    inv_ids = [inv.id for inv in db.query(Invoice.id).filter(Invoice.patient_id == patient.id).all()]
    if inv_ids:
        db.query(InvoiceLineItem).filter(InvoiceLineItem.invoice_id.in_(inv_ids)).delete(synchronize_session=False)
        db.query(Invoice).filter(Invoice.id.in_(inv_ids)).delete(synchronize_session=False)

    # 2. Clinical documents & stored files
    docs = db.query(ClinicalDocument).filter(ClinicalDocument.patient_id == patient.id).all()
    storage_names = [d.storage_filename for d in docs if d.storage_filename]
    db.query(ClinicalDocument).filter(ClinicalDocument.patient_id == patient.id).delete(synchronize_session=False)

    # 3. Prescriptions
    rx_ids = [rx.id for rx in db.query(Prescription.id).filter(Prescription.patient_id == patient.id).all()]
    if rx_ids:
        db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id.in_(rx_ids)).delete(synchronize_session=False)
        db.query(Prescription).filter(Prescription.id.in_(rx_ids)).delete(synchronize_session=False)

    # 4. Treatments & Plans
    db.query(TreatmentRecord).filter(TreatmentRecord.patient_id == patient.id).delete(synchronize_session=False)
    plan_ids = [tp.id for tp in db.query(TreatmentPlan.id).filter(TreatmentPlan.patient_id == patient.id).all()]
    if plan_ids:
        db.query(TreatmentPlanItem).filter(TreatmentPlanItem.treatment_plan_id.in_(plan_ids)).delete(
            synchronize_session=False
        )
        db.query(TreatmentPlan).filter(TreatmentPlan.id.in_(plan_ids)).delete(synchronize_session=False)

    # 5. Diagnoses, Dental Chart & Encounters
    db.query(Diagnosis).filter(Diagnosis.patient_id == patient.id).delete(synchronize_session=False)
    db.query(ToothFinding).filter(ToothFinding.patient_id == patient.id).delete(synchronize_session=False)
    db.query(DentalChartTooth).filter(DentalChartTooth.patient_id == patient.id).delete(synchronize_session=False)
    db.query(RecordCorrectionRequest).filter(RecordCorrectionRequest.patient_id == patient.id).delete(
        synchronize_session=False
    )
    enc_ids = [e.id for e in db.query(ClinicalEncounter.id).filter(ClinicalEncounter.patient_id == patient.id).all()]
    if enc_ids:
        db.query(EncounterAmendment).filter(EncounterAmendment.encounter_id.in_(enc_ids)).delete(
            synchronize_session=False
        )
        db.query(ClinicalEncounter).filter(ClinicalEncounter.id.in_(enc_ids)).delete(synchronize_session=False)

    # 6. Appointments
    db.query(Appointment).filter(Appointment.patient_id == patient.id).update(
        {"rescheduled_from_id": None}, synchronize_session=False
    )
    db.query(Appointment).filter(Appointment.patient_id == patient.id).delete(synchronize_session=False)

    # 7. Medical History, Allergies, Consents, Reviews
    db.query(Allergy).filter(Allergy.patient_id == patient.id).delete(synchronize_session=False)
    db.query(MedicalHistory).filter(MedicalHistory.patient_id == patient.id).delete(synchronize_session=False)
    db.query(ConsentRecord).filter(ConsentRecord.patient_id == patient.id).delete(synchronize_session=False)
    db.query(Review).filter(Review.patient_id == patient.id).delete(synchronize_session=False)

    # 8. Delete PatientProfile and linked Patient User account
    db.delete(patient)
    db.flush()

    if linked_user_id:
        linked_user = db.query(User).filter(User.id == linked_user_id).first()
        if linked_user and linked_user.role and linked_user.role.name == ROLE_PATIENT:
            db.query(Notification).filter(Notification.user_id == linked_user.id).delete(synchronize_session=False)
            db.query(PasswordResetToken).filter(PasswordResetToken.user_id == linked_user.id).delete(
                synchronize_session=False
            )
            db.query(ConsentRecord).filter(ConsentRecord.user_id == linked_user.id).delete(synchronize_session=False)
            db.query(Review).filter(Review.user_id == linked_user.id).delete(synchronize_session=False)
            db.delete(linked_user)

    log_audit_event(
        db=db,
        action="ADMIN_DELETED_PATIENT",
        resource_type="patient_profile",
        actor=current_user,
        resource_id=patient_id,
        patient_id=patient_id,
        request=request,
        details={"patient_number": patient_number, "full_name": patient_name},
    )
    db.commit()

    for sname in set(storage_names):
        if db.query(ClinicalDocument).filter(ClinicalDocument.storage_filename == sname).count() == 0:
            fpath = settings.private_upload_dir / sname
            if fpath.exists():
                try:
                    fpath.unlink()
                except OSError:
                    pass

    return {
        "message": f"Patient {patient_name} ({patient_number}) has been deleted.",
        "deleted_patient_id": patient_id,
    }
