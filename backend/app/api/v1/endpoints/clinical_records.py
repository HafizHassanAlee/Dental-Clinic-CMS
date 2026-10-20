from datetime import date, datetime, timezone
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from app.core.permissions import ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import log_audit_event
from app.db.session import get_db
from app.dependencies.auth import (
    get_current_doctor_profile,
    get_current_user,
    require_roles,
    verify_patient_isolation,
)
from app.models.entities import (
    ClinicalEncounter,
    Diagnosis,
    DoctorProfile,
    EncounterAmendment,
    PatientProfile,
    User,
)
from app.schemas.domain import (
    ClinicalEncounterCreateRequest,
    ClinicalEncounterUpdateRequest,
    DiagnosisCreateRequest,
)


router = APIRouter()


def _serialize_encounter(e: ClinicalEncounter) -> dict:
    return {
        "id": e.id,
        "encounter_number": e.encounter_number,
        "patient_id": e.patient_id,
        "patient_name": e.patient.full_name if e.patient else "",
        "patient_number": e.patient.patient_number if e.patient else "",
        "doctor_id": e.doctor_id,
        "doctor_name": e.doctor.full_name if e.doctor else "Dr. Aisha Salman",
        "appointment_id": e.appointment_id,
        "visit_date": e.visit_date.isoformat(),
        "presenting_complaint": e.presenting_complaint,
        "history_of_present_illness": e.history_of_present_illness,
        "medical_history_summary": e.medical_history_summary,
        "allergies_summary": e.allergies_summary,
        "examination_findings": e.examination_findings,
        "extra_oral_findings": e.extra_oral_findings,
        "intra_oral_findings": e.intra_oral_findings,
        "tooth_specific_findings": e.tooth_specific_findings,
        "diagnosis_summary": e.diagnosis_summary,
        "treatment_performed": e.treatment_performed,
        "treatment_plan_notes": e.treatment_plan_notes,
        "follow_up_instructions": e.follow_up_instructions,
        "next_recommended_visit_date": e.next_recommended_visit_date.isoformat()
        if e.next_recommended_visit_date
        else None,
        "status": e.status,
        "version": e.version,
        "finalized_at": e.finalized_at.isoformat() if e.finalized_at else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "diagnoses": [
            {
                "id": d.id,
                "tooth_fdi": d.tooth_fdi,
                "diagnosis_code": d.diagnosis_code,
                "diagnosis_title": d.diagnosis_title,
                "severity": d.severity,
                "clinical_notes": d.clinical_notes,
                "status": d.status,
            }
            for d in e.diagnoses
        ],
        "amendments": [
            {
                "id": a.id,
                "version_number": a.version_number,
                "amendment_reason": a.amendment_reason,
                "created_at": a.created_at.isoformat(),
            }
            for a in e.amendments
        ],
    }


@router.get("")
def list_clinical_encounters(
    patient_id: Optional[int] = Query(default=None),
    visit_date: Optional[date] = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = current_user.role.name if current_user.role else ""
    query = db.query(ClinicalEncounter)

    if role_name == ROLE_PATIENT:
        own = db.query(PatientProfile).filter(PatientProfile.user_id == current_user.id).first()
        if not own:
            return []
        if patient_id is not None and patient_id != own.id:
            verify_patient_isolation(db, current_user, patient_id, request, "clinical_encounter")
        query = query.filter(ClinicalEncounter.patient_id == own.id)
    else:
        if patient_id is not None:
            verify_patient_isolation(db, current_user, patient_id, request, "clinical_encounter")
            query = query.filter(ClinicalEncounter.patient_id == patient_id)

    if visit_date is not None:
        query = query.filter(ClinicalEncounter.visit_date == visit_date)

    items = query.order_by(ClinicalEncounter.visit_date.desc(), ClinicalEncounter.id.desc()).all()
    return [_serialize_encounter(e) for e in items]


@router.get("/{encounter_id}")
def get_clinical_encounter(
    encounter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enc = db.query(ClinicalEncounter).filter(ClinicalEncounter.id == encounter_id).first()
    if not enc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinical record not found.")

    verify_patient_isolation(db, current_user, enc.patient_id, request, "clinical_encounter")
    log_audit_event(
        db=db,
        action="CLINICAL_ENCOUNTER_VIEWED",
        resource_type="clinical_encounter",
        actor=current_user,
        resource_id=enc.id,
        patient_id=enc.patient_id,
        request=request,
    )
    db.commit()
    return _serialize_encounter(enc)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_clinical_encounter(
    payload: ClinicalEncounterCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR)),
    doctor: DoctorProfile = Depends(get_current_doctor_profile),
):
    """Only authorized clinical staff (Doctors) can create clinical encounters."""
    patient = db.query(PatientProfile).filter(PatientProfile.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    year = datetime.now(timezone.utc).year
    next_seq = db.query(ClinicalEncounter).count() + 1
    enc_num = f"ENC-{year}-{next_seq:05d}"
    while db.query(ClinicalEncounter).filter(ClinicalEncounter.encounter_number == enc_num).first():
        next_seq += 1
        enc_num = f"ENC-{year}-{next_seq:05d}"

    now = datetime.now(timezone.utc)
    status_val = "Finalized" if payload.finalize else "Draft"

    enc = ClinicalEncounter(
        encounter_number=enc_num,
        patient_id=patient.id,
        doctor_id=doctor.id,
        appointment_id=payload.appointment_id,
        visit_date=payload.visit_date or date.today(),
        presenting_complaint=payload.presenting_complaint.strip(),
        history_of_present_illness=payload.history_of_present_illness,
        medical_history_summary=payload.medical_history_summary,
        allergies_summary=payload.allergies_summary,
        examination_findings=payload.examination_findings,
        extra_oral_findings=payload.extra_oral_findings,
        intra_oral_findings=payload.intra_oral_findings,
        tooth_specific_findings=payload.tooth_specific_findings,
        diagnosis_summary=payload.diagnosis_summary,
        treatment_performed=payload.treatment_performed,
        treatment_plan_notes=payload.treatment_plan_notes,
        follow_up_instructions=payload.follow_up_instructions,
        next_recommended_visit_date=payload.next_recommended_visit_date,
        status=status_val,
        version=1,
        finalized_at=now if payload.finalize else None,
        finalized_by_id=current_user.id if payload.finalize else None,
        created_by_id=current_user.id,
        updated_by_id=current_user.id,
    )
    db.add(enc)
    db.flush()

    log_audit_event(
        db=db,
        action="CLINICAL_ENCOUNTER_CREATED",
        resource_type="clinical_encounter",
        actor=current_user,
        resource_id=enc.id,
        patient_id=patient.id,
        request=request,
        details={"encounter_number": enc_num, "status": status_val},
    )
    db.commit()
    db.refresh(enc)
    return _serialize_encounter(enc)


@router.put("/{encounter_id}")
def update_or_amend_clinical_encounter(
    encounter_id: int,
    payload: ClinicalEncounterUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR)),
):
    """
    Updates a Draft clinical encounter, or records a versioned amendment if the note was already Finalized.
    Never silently overwrites finalized clinical notes.
    """
    enc = db.query(ClinicalEncounter).filter(ClinicalEncounter.id == encounter_id).first()
    if not enc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinical encounter not found.")

    was_finalized = enc.status in {"Finalized", "Amended"}
    if was_finalized and not (payload.amendment_reason and payload.amendment_reason.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Finalized clinical notes cannot be overwritten without an explicit amendment_reason.",
        )

    prev_snapshot = {
        "presenting_complaint": enc.presenting_complaint,
        "examination_findings": enc.examination_findings,
        "diagnosis_summary": enc.diagnosis_summary,
        "treatment_performed": enc.treatment_performed,
        "follow_up_instructions": enc.follow_up_instructions,
    }

    editable_fields = [
        "presenting_complaint",
        "history_of_present_illness",
        "medical_history_summary",
        "allergies_summary",
        "examination_findings",
        "extra_oral_findings",
        "intra_oral_findings",
        "tooth_specific_findings",
        "diagnosis_summary",
        "treatment_performed",
        "treatment_plan_notes",
        "follow_up_instructions",
        "next_recommended_visit_date",
    ]
    data = payload.model_dump(exclude_unset=True)
    for field in editable_fields:
        if field in data:
            setattr(enc, field, data[field])

    now = datetime.now(timezone.utc)
    enc.updated_by_id = current_user.id

    if was_finalized:
        enc.version += 1
        enc.status = "Amended"
        new_snapshot = {
            "presenting_complaint": enc.presenting_complaint,
            "examination_findings": enc.examination_findings,
            "diagnosis_summary": enc.diagnosis_summary,
            "treatment_performed": enc.treatment_performed,
            "follow_up_instructions": enc.follow_up_instructions,
        }
        db.add(
            EncounterAmendment(
                encounter_id=enc.id,
                version_number=enc.version,
                amendment_reason=payload.amendment_reason.strip(),
                previous_snapshot_json=json.dumps(prev_snapshot, default=str),
                updated_snapshot_json=json.dumps(new_snapshot, default=str),
                amended_by_id=current_user.id,
            )
        )
        action_name = "CLINICAL_ENCOUNTER_AMENDED"
    else:
        if payload.finalize:
            enc.status = "Finalized"
            enc.finalized_at = now
            enc.finalized_by_id = current_user.id
        action_name = "CLINICAL_ENCOUNTER_UPDATED"

    log_audit_event(
        db=db,
        action=action_name,
        resource_type="clinical_encounter",
        actor=current_user,
        resource_id=enc.id,
        patient_id=enc.patient_id,
        request=request,
        details={"version": enc.version, "status": enc.status},
    )
    db.commit()
    db.refresh(enc)
    return _serialize_encounter(enc)


@router.post("/diagnoses", status_code=status.HTTP_201_CREATED)
def create_diagnosis(
    payload: DiagnosisCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR)),
    doctor: DoctorProfile = Depends(get_current_doctor_profile),
):
    verify_patient_isolation(db, current_user, payload.patient_id, request, "diagnosis")
    diag = Diagnosis(
        encounter_id=payload.encounter_id,
        patient_id=payload.patient_id,
        doctor_id=doctor.id,
        tooth_fdi=payload.tooth_fdi,
        diagnosis_code=payload.diagnosis_code,
        diagnosis_title=payload.diagnosis_title.strip(),
        severity=payload.severity,
        clinical_notes=payload.clinical_notes,
        status=payload.status,
    )
    db.add(diag)
    log_audit_event(
        db=db,
        action="DIAGNOSIS_RECORDED",
        resource_type="diagnosis",
        actor=current_user,
        patient_id=payload.patient_id,
        request=request,
        details={"diagnosis_title": diag.diagnosis_title, "tooth_fdi": diag.tooth_fdi},
    )
    db.commit()
    db.refresh(diag)
    return {
        "id": diag.id,
        "patient_id": diag.patient_id,
        "tooth_fdi": diag.tooth_fdi,
        "diagnosis_code": diag.diagnosis_code,
        "diagnosis_title": diag.diagnosis_title,
        "severity": diag.severity,
        "clinical_notes": diag.clinical_notes,
        "status": diag.status,
    }
