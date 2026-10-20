from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.permissions import ROLE_DOCTOR
from app.core.security import log_audit_event
from app.db.session import get_db
from app.dependencies.auth import (
    get_current_doctor_profile,
    get_current_patient_profile,
    get_current_user,
    require_roles,
    verify_patient_isolation,
)
from app.models.entities import DentalChartTooth, DoctorProfile, PatientProfile, ToothFinding, User
from app.schemas.domain import ToothChartUpdateRequest
from app.services.dental_chart_catalog import (
    ALL_FDI_MAP,
    ALLOWED_TOOTH_CONDITIONS,
    get_patient_dental_chart,
)


router = APIRouter()


@router.get("/me")
def get_my_dental_chart(
    db: Session = Depends(get_db),
    patient: PatientProfile = Depends(get_current_patient_profile),
):
    return get_patient_dental_chart(db, patient.id)


@router.get("/{patient_id}")
def get_dental_chart_for_patient(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = verify_patient_isolation(db, current_user, patient_id, request, "dental_chart")
    return get_patient_dental_chart(db, patient.id)


@router.put("/{patient_id}/tooth")
def update_patient_tooth_finding(
    patient_id: int,
    payload: ToothChartUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR)),
    doctor: DoctorProfile = Depends(get_current_doctor_profile),
):
    """
    Only authorized Doctors can record or modify tooth-specific findings on the FDI dental chart.
    Patients can view their dental chart but receive 403 Forbidden if they attempt modifications.
    """
    patient = verify_patient_isolation(db, current_user, patient_id, request, "dental_chart")
    fdi = payload.tooth_fdi.strip()
    if fdi not in ALL_FDI_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid FDI tooth number '{fdi}'. Must be a valid permanent (11-48) or primary (51-85) FDI code.",
        )

    if payload.condition_status not in ALLOWED_TOOTH_CONDITIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tooth condition '{payload.condition_status}'. Allowed: {sorted(ALLOWED_TOOTH_CONDITIONS)}",
        )

    meta = ALL_FDI_MAP[fdi]
    chart_tooth = (
        db.query(DentalChartTooth)
        .filter(DentalChartTooth.patient_id == patient.id, DentalChartTooth.tooth_fdi == fdi)
        .first()
    )
    if not chart_tooth:
        chart_tooth = DentalChartTooth(
            patient_id=patient.id,
            tooth_fdi=fdi,
            dentition_type=meta["dentition_type"],
            tooth_name=meta["name"],
        )
        db.add(chart_tooth)
        db.flush()

    chart_tooth.condition_status = payload.condition_status
    chart_tooth.surfaces = payload.surfaces
    chart_tooth.mobility_grade = payload.mobility_grade
    chart_tooth.clinical_notes = payload.clinical_notes
    chart_tooth.updated_by_doctor_id = doctor.id

    finding = ToothFinding(
        chart_tooth_id=chart_tooth.id,
        patient_id=patient.id,
        encounter_id=payload.encounter_id,
        doctor_id=doctor.id,
        tooth_fdi=fdi,
        condition_status=payload.condition_status,
        surfaces=payload.surfaces,
        finding_notes=payload.clinical_notes or f"Updated tooth #{fdi} status to {payload.condition_status}",
        treatment_recommended=payload.treatment_recommended,
    )
    db.add(finding)

    log_audit_event(
        db=db,
        action="DENTAL_CHART_TOOTH_UPDATED",
        resource_type="dental_chart_tooth",
        actor=current_user,
        resource_id=chart_tooth.id,
        patient_id=patient.id,
        request=request,
        details={"tooth_fdi": fdi, "condition_status": payload.condition_status},
    )
    db.commit()
    return get_patient_dental_chart(db, patient.id)
