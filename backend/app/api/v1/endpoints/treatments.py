from datetime import date, datetime, timezone
from decimal import Decimal
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
    DoctorProfile,
    PatientProfile,
    TreatmentPlan,
    TreatmentPlanItem,
    TreatmentRecord,
    User,
)
from app.schemas.domain import (
    TreatmentPlanCreateRequest,
    TreatmentRecordCreateRequest,
)


router = APIRouter()


def _serialize_plan(p: TreatmentPlan) -> dict:
    return {
        "id": p.id,
        "plan_number": p.plan_number,
        "patient_id": p.patient_id,
        "patient_name": p.patient.full_name if p.patient else "",
        "doctor_id": p.doctor_id,
        "doctor_name": p.doctor.full_name if p.doctor else "Dr. Aisha Salman",
        "encounter_id": p.encounter_id,
        "title": p.title,
        "clinical_summary": p.clinical_summary,
        "status": p.status,
        "total_estimated_cost": float(p.total_estimated_cost),
        "currency": "PKR",
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "items": [
            {
                "id": item.id,
                "service_id": item.service_id,
                "tooth_fdi": item.tooth_fdi,
                "procedure_name": item.procedure_name,
                "estimated_cost": float(item.estimated_cost),
                "priority": item.priority,
                "status": item.status,
                "scheduled_date": item.scheduled_date.isoformat() if item.scheduled_date else None,
                "notes": item.notes,
            }
            for item in p.items
        ],
    }


def _serialize_record(r: TreatmentRecord) -> dict:
    return {
        "id": r.id,
        "record_number": r.record_number,
        "patient_id": r.patient_id,
        "patient_name": r.patient.full_name if r.patient else "",
        "doctor_id": r.doctor_id,
        "doctor_name": r.doctor.full_name if r.doctor else "Dr. Aisha Salman",
        "appointment_id": r.appointment_id,
        "encounter_id": r.encounter_id,
        "tooth_fdi": r.tooth_fdi,
        "surface": r.surface,
        "procedure_name": r.procedure_name,
        "clinical_description": r.clinical_description,
        "materials_used": r.materials_used,
        "complications": r.complications,
        "post_op_instructions": r.post_op_instructions,
        "follow_up_recommended": r.follow_up_recommended.isoformat() if r.follow_up_recommended else None,
        "performed_date": r.performed_date.isoformat(),
    }


@router.get("/plans")
def list_treatment_plans(
    patient_id: Optional[int] = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = current_user.role.name if current_user.role else ""
    query = db.query(TreatmentPlan)
    if role_name == ROLE_PATIENT:
        own = db.query(PatientProfile).filter(PatientProfile.user_id == current_user.id).first()
        if not own:
            return []
        if patient_id is not None and patient_id != own.id:
            verify_patient_isolation(db, current_user, patient_id, request, "treatment_plan")
        query = query.filter(TreatmentPlan.patient_id == own.id)
    elif patient_id is not None:
        verify_patient_isolation(db, current_user, patient_id, request, "treatment_plan")
        query = query.filter(TreatmentPlan.patient_id == patient_id)

    plans = query.order_by(TreatmentPlan.created_at.desc()).all()
    return [_serialize_plan(p) for p in plans]


@router.post("/plans", status_code=status.HTTP_201_CREATED)
def create_treatment_plan(
    payload: TreatmentPlanCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR)),
    doctor: DoctorProfile = Depends(get_current_doctor_profile),
):
    verify_patient_isolation(db, current_user, payload.patient_id, request, "treatment_plan")

    year = datetime.now(timezone.utc).year
    next_seq = db.query(TreatmentPlan).count() + 1
    plan_num = f"TP-{year}-{next_seq:05d}"
    while db.query(TreatmentPlan).filter(TreatmentPlan.plan_number == plan_num).first():
        next_seq += 1
        plan_num = f"TP-{year}-{next_seq:05d}"

    total_est = sum((Decimal(str(i.estimated_cost)) for i in payload.items), Decimal("0.00"))
    plan = TreatmentPlan(
        plan_number=plan_num,
        patient_id=payload.patient_id,
        doctor_id=doctor.id,
        encounter_id=payload.encounter_id,
        title=payload.title.strip(),
        clinical_summary=payload.clinical_summary,
        status="Proposed",
        total_estimated_cost=total_est,
    )
    db.add(plan)
    db.flush()

    for item in payload.items:
        db.add(
            TreatmentPlanItem(
                treatment_plan_id=plan.id,
                service_id=item.service_id,
                tooth_fdi=item.tooth_fdi,
                procedure_name=item.procedure_name.strip(),
                estimated_cost=Decimal(str(item.estimated_cost)),
                priority=item.priority,
                status="Planned",
                scheduled_date=item.scheduled_date,
                notes=item.notes,
            )
        )

    log_audit_event(
        db=db,
        action="TREATMENT_PLAN_CREATED",
        resource_type="treatment_plan",
        actor=current_user,
        resource_id=plan.id,
        patient_id=payload.patient_id,
        request=request,
        details={"plan_number": plan_num, "total_estimated_cost": str(total_est)},
    )
    db.commit()
    db.refresh(plan)
    return _serialize_plan(plan)


@router.patch("/plans/{plan_id}/status")
def update_treatment_plan_status(
    plan_id: int,
    status_val: str = Query(..., alias="status"),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR)),
):
    plan = db.query(TreatmentPlan).filter(TreatmentPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Treatment plan not found.")
    plan.status = status_val
    log_audit_event(
        db=db,
        action="TREATMENT_PLAN_STATUS_UPDATED",
        resource_type="treatment_plan",
        actor=current_user,
        resource_id=plan.id,
        patient_id=plan.patient_id,
        request=request,
        details={"status": status_val},
    )
    db.commit()
    db.refresh(plan)
    return _serialize_plan(plan)


@router.get("/records")
def list_treatment_records(
    patient_id: Optional[int] = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = current_user.role.name if current_user.role else ""
    query = db.query(TreatmentRecord)
    if role_name == ROLE_PATIENT:
        own = db.query(PatientProfile).filter(PatientProfile.user_id == current_user.id).first()
        if not own:
            return []
        if patient_id is not None and patient_id != own.id:
            verify_patient_isolation(db, current_user, patient_id, request, "treatment_record")
        query = query.filter(TreatmentRecord.patient_id == own.id)
    elif patient_id is not None:
        verify_patient_isolation(db, current_user, patient_id, request, "treatment_record")
        query = query.filter(TreatmentRecord.patient_id == patient_id)

    records = query.order_by(TreatmentRecord.performed_date.desc(), TreatmentRecord.id.desc()).all()
    return [_serialize_record(r) for r in records]


@router.post("/records", status_code=status.HTTP_201_CREATED)
def create_treatment_record(
    payload: TreatmentRecordCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR)),
    doctor: DoctorProfile = Depends(get_current_doctor_profile),
):
    verify_patient_isolation(db, current_user, payload.patient_id, request, "treatment_record")

    year = datetime.now(timezone.utc).year
    next_seq = db.query(TreatmentRecord).count() + 1
    rec_num = f"TR-{year}-{next_seq:05d}"
    while db.query(TreatmentRecord).filter(TreatmentRecord.record_number == rec_num).first():
        next_seq += 1
        rec_num = f"TR-{year}-{next_seq:05d}"

    rec = TreatmentRecord(
        record_number=rec_num,
        patient_id=payload.patient_id,
        doctor_id=doctor.id,
        appointment_id=payload.appointment_id,
        encounter_id=payload.encounter_id,
        treatment_plan_item_id=payload.treatment_plan_item_id,
        service_id=payload.service_id,
        tooth_fdi=payload.tooth_fdi,
        surface=payload.surface,
        procedure_name=payload.procedure_name.strip(),
        clinical_description=payload.clinical_description.strip(),
        materials_used=payload.materials_used,
        complications=payload.complications,
        post_op_instructions=payload.post_op_instructions,
        follow_up_recommended=payload.follow_up_recommended,
        performed_date=payload.performed_date or date.today(),
    )
    db.add(rec)

    if payload.treatment_plan_item_id:
        tp_item = (
            db.query(TreatmentPlanItem)
            .filter(TreatmentPlanItem.id == payload.treatment_plan_item_id)
            .first()
        )
        if tp_item:
            tp_item.status = "Completed"
            tp_item.completed_at = datetime.now(timezone.utc)

    log_audit_event(
        db=db,
        action="TREATMENT_RECORD_CREATED",
        resource_type="treatment_record",
        actor=current_user,
        patient_id=payload.patient_id,
        request=request,
        details={"record_number": rec_num, "procedure_name": rec.procedure_name},
    )
    db.commit()
    db.refresh(rec)
    return _serialize_record(rec)
