from datetime import date, datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
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
    ClinicSetting,
    DoctorProfile,
    PatientProfile,
    Prescription,
    PrescriptionItem,
    User,
)
from app.schemas.domain import PrescriptionCreateRequest
from app.services.notification_service import create_user_notification
from app.services.pdf_service import generate_prescription_pdf


router = APIRouter()


def _serialize_prescription(rx: Prescription) -> dict:
    return {
        "id": rx.id,
        "prescription_number": rx.prescription_number,
        "patient_id": rx.patient_id,
        "patient_name": rx.patient.full_name if rx.patient else "",
        "patient_number": rx.patient.patient_number if rx.patient else "",
        "doctor_id": rx.doctor_id,
        "doctor_name": rx.doctor.full_name if rx.doctor else "Dr. Aisha Salman",
        "encounter_id": rx.encounter_id,
        "appointment_id": rx.appointment_id,
        "issue_date": rx.issue_date.isoformat(),
        "diagnosis_notes": rx.diagnosis_notes,
        "general_instructions": rx.general_instructions,
        "items": [
            {
                "id": item.id,
                "medication_name": item.medication_name,
                "strength": item.strength,
                "dosage": item.dosage,
                "route": item.route,
                "frequency": item.frequency,
                "duration": item.duration,
                "quantity": item.quantity,
                "instructions": item.instructions,
            }
            for item in rx.items
        ],
    }


@router.get("")
def list_prescriptions(
    patient_id: Optional[int] = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = current_user.role.name if current_user.role else ""
    query = db.query(Prescription)
    if role_name == ROLE_PATIENT:
        own = db.query(PatientProfile).filter(PatientProfile.user_id == current_user.id).first()
        if not own:
            return []
        if patient_id is not None and patient_id != own.id:
            verify_patient_isolation(db, current_user, patient_id, request, "prescription")
        query = query.filter(Prescription.patient_id == own.id)
    elif patient_id is not None:
        verify_patient_isolation(db, current_user, patient_id, request, "prescription")
        query = query.filter(Prescription.patient_id == patient_id)

    items = query.order_by(Prescription.issue_date.desc(), Prescription.id.desc()).all()
    return [_serialize_prescription(rx) for rx in items]


@router.get("/{prescription_id}")
def get_prescription(
    prescription_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rx = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not rx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found.")

    verify_patient_isolation(db, current_user, rx.patient_id, request, "prescription")
    return _serialize_prescription(rx)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_prescription(
    payload: PrescriptionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR)),
    doctor: DoctorProfile = Depends(get_current_doctor_profile),
):
    """Only authorized clinicians (Doctors) can issue prescriptions."""
    patient = verify_patient_isolation(db, current_user, payload.patient_id, request, "prescription")

    year = datetime.now(timezone.utc).year
    next_seq = db.query(Prescription).count() + 1
    rx_num = f"RX-{year}-{next_seq:05d}"
    while db.query(Prescription).filter(Prescription.prescription_number == rx_num).first():
        next_seq += 1
        rx_num = f"RX-{year}-{next_seq:05d}"

    rx = Prescription(
        prescription_number=rx_num,
        patient_id=patient.id,
        doctor_id=doctor.id,
        encounter_id=payload.encounter_id,
        appointment_id=payload.appointment_id,
        issue_date=date.today(),
        diagnosis_notes=payload.diagnosis_notes,
        general_instructions=payload.general_instructions,
    )
    db.add(rx)
    db.flush()

    for item in payload.items:
        db.add(
            PrescriptionItem(
                prescription_id=rx.id,
                medication_name=item.medication_name.strip(),
                strength=item.strength,
                dosage=item.dosage.strip(),
                route=item.route,
                frequency=item.frequency.strip(),
                duration=item.duration.strip(),
                quantity=item.quantity,
                instructions=item.instructions,
            )
        )

    if patient.user_id:
        create_user_notification(
            db=db,
            user_id=patient.user_id,
            title=f"New Prescription Issued ({rx_num})",
            message=f"{doctor.full_name} has issued a new clinical prescription ({rx_num}) to your patient portal.",
            notification_type="Prescription",
            related_entity_type="prescription",
            related_entity_id=rx.id,
        )

    log_audit_event(
        db=db,
        action="PRESCRIPTION_ISSUED",
        resource_type="prescription",
        actor=current_user,
        resource_id=rx.id,
        patient_id=patient.id,
        request=request,
        details={"prescription_number": rx_num, "medications_count": len(payload.items)},
    )
    db.commit()
    db.refresh(rx)
    return _serialize_prescription(rx)


@router.get("/{prescription_id}/pdf")
def download_prescription_pdf(
    prescription_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rx = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not rx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found.")

    verify_patient_isolation(db, current_user, rx.patient_id, request, "prescription")
    clinic = db.query(ClinicSetting).first() or ClinicSetting()
    pdf_bytes = generate_prescription_pdf(rx, clinic)

    log_audit_event(
        db=db,
        action="PRESCRIPTION_PDF_DOWNLOADED",
        resource_type="prescription",
        actor=current_user,
        resource_id=rx.id,
        patient_id=rx.patient_id,
        request=request,
    )
    db.commit()

    filename = f"RumiDentalCare_{rx.prescription_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
