from datetime import date, time
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.permissions import ROLE_ADMIN, ROLE_DOCTOR
from app.core.security import hash_password, log_audit_event, validate_password_strength
from app.db.session import get_db
from app.dependencies.auth import get_current_doctor_profile, require_roles
from app.models.entities import (
    Appointment,
    ClinicalEncounter,
    DoctorProfile,
    DoctorSchedule,
    Role,
    TreatmentPlan,
    User,
)
from app.schemas.domain import (
    AdminCreateDoctorRequest,
    DoctorScheduleItemInput,
    DoctorUpdateRequest,
)


router = APIRouter()


def _serialize_doctor(doc: DoctorProfile) -> dict:
    return {
        "id": doc.id,
        "user_id": doc.user_id,
        "doctor_code": doc.doctor_code,
        "full_name": doc.full_name,
        "email": doc.user.email if doc.user else None,
        "phone": doc.user.phone if doc.user else None,
        "title": doc.title,
        "specialization": doc.specialization,
        "qualification": doc.qualification,
        "license_number": doc.license_number,
        "bio": doc.bio,
        "consultation_fee": float(doc.consultation_fee),
        "slot_duration_minutes": doc.slot_duration_minutes,
        "branch_code": doc.branch_code,
        "is_active": doc.is_active,
        "is_public": doc.is_public,
        "schedules": [
            {
                "day_of_week": s.day_of_week,
                "start_time": s.start_time.strftime("%H:%M"),
                "end_time": s.end_time.strftime("%H:%M"),
                "break_start": s.break_start.strftime("%H:%M") if s.break_start else None,
                "break_end": s.break_end.strftime("%H:%M") if s.break_end else None,
                "slot_duration_minutes": s.slot_duration_minutes,
                "is_available": s.is_available,
            }
            for s in sorted(doc.schedules, key=lambda x: x.day_of_week)
        ],
    }


@router.get("/public")
def list_public_doctors(db: Session = Depends(get_db)):
    docs = (
        db.query(DoctorProfile)
        .filter(DoctorProfile.is_active.is_(True), DoctorProfile.is_public.is_(True))
        .order_by(DoctorProfile.id.asc())
        .all()
    )
    return [
        {
            "id": d.id,
            "doctor_code": d.doctor_code,
            "full_name": d.full_name,
            "title": d.title,
            "specialization": d.specialization,
            "bio": d.bio,
            "consultation_fee": float(d.consultation_fee),
            "slot_duration_minutes": d.slot_duration_minutes,
        }
        for d in docs
    ]


@router.get("/me/dashboard")
def get_doctor_dashboard(
    db: Session = Depends(get_db),
    doctor: DoctorProfile = Depends(get_current_doctor_profile),
):
    today = date.today()
    todays_apts = (
        db.query(Appointment)
        .filter(Appointment.doctor_id == doctor.id, Appointment.appointment_date == today)
        .order_by(Appointment.start_time.asc())
        .all()
    )
    upcoming_apts = (
        db.query(Appointment)
        .filter(
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date > today,
            Appointment.status.in_(["Requested", "Confirmed"]),
        )
        .order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
        .limit(15)
        .all()
    )
    completed_count = (
        db.query(Appointment)
        .filter(Appointment.doctor_id == doctor.id, Appointment.status == "Completed")
        .count()
    )
    draft_encounters = (
        db.query(ClinicalEncounter)
        .filter(ClinicalEncounter.doctor_id == doctor.id, ClinicalEncounter.status == "Draft")
        .order_by(ClinicalEncounter.visit_date.desc())
        .all()
    )
    follow_up_encounters = (
        db.query(ClinicalEncounter)
        .filter(
            ClinicalEncounter.doctor_id == doctor.id,
            ClinicalEncounter.next_recommended_visit_date.isnot(None),
            ClinicalEncounter.next_recommended_visit_date >= today,
        )
        .order_by(ClinicalEncounter.next_recommended_visit_date.asc())
        .limit(10)
        .all()
    )
    active_plans_count = (
        db.query(TreatmentPlan)
        .filter(TreatmentPlan.doctor_id == doctor.id, TreatmentPlan.status.in_(["Proposed", "InProgress"]))
        .count()
    )

    return {
        "doctor": _serialize_doctor(doctor),
        "metrics": {
            "todays_appointments_count": len(todays_apts),
            "upcoming_appointments_count": len(upcoming_apts),
            "completed_consultations_count": completed_count,
            "pending_clinical_docs_count": len(draft_encounters),
            "follow_up_cases_count": len(follow_up_encounters),
            "active_treatment_plans_count": active_plans_count,
        },
        "todays_appointments": [
            {
                "id": a.id,
                "appointment_number": a.appointment_number,
                "patient_id": a.patient_id,
                "patient_name": a.patient.full_name if a.patient else "",
                "patient_number": a.patient.patient_number if a.patient else "",
                "start_time": a.start_time.strftime("%H:%M"),
                "end_time": a.end_time.strftime("%H:%M"),
                "status": a.status,
                "service_name": a.service.name if a.service else "Dental Consultation",
                "reason_for_visit": a.reason_for_visit,
            }
            for a in todays_apts
        ],
        "upcoming_appointments": [
            {
                "id": a.id,
                "appointment_number": a.appointment_number,
                "patient_id": a.patient_id,
                "patient_name": a.patient.full_name if a.patient else "",
                "appointment_date": a.appointment_date.isoformat(),
                "start_time": a.start_time.strftime("%H:%M"),
                "status": a.status,
                "service_name": a.service.name if a.service else "Dental Consultation",
            }
            for a in upcoming_apts
        ],
        "pending_documentation": [
            {
                "id": e.id,
                "encounter_number": e.encounter_number,
                "patient_id": e.patient_id,
                "patient_name": e.patient.full_name if e.patient else "",
                "visit_date": e.visit_date.isoformat(),
                "presenting_complaint": e.presenting_complaint,
            }
            for e in draft_encounters
        ],
        "follow_up_cases": [
            {
                "id": e.id,
                "encounter_number": e.encounter_number,
                "patient_id": e.patient_id,
                "patient_name": e.patient.full_name if e.patient else "",
                "next_recommended_visit_date": e.next_recommended_visit_date.isoformat(),
                "diagnosis_summary": e.diagnosis_summary,
            }
            for e in follow_up_encounters
        ],
    }


@router.get("")
def list_all_doctors(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR, ROLE_ADMIN)),
):
    docs = db.query(DoctorProfile).order_by(DoctorProfile.id.asc()).all()
    return [_serialize_doctor(d) for d in docs]


@router.post("", status_code=status.HTTP_201_CREATED)
def admin_create_doctor(
    payload: AdminCreateDoctorRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Only an authorized Administrator can create Doctor accounts."""
    err = validate_password_strength(payload.password)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    email_norm = payload.email.strip().lower()
    if db.query(User).filter(User.email == email_norm).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    doctor_role = db.query(Role).filter(Role.name == ROLE_DOCTOR).first()
    user = User(
        email=email_norm,
        phone=payload.phone.strip(),
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role_id=doctor_role.id,
        is_active=True,
        is_email_verified=True,
    )
    db.add(user)
    db.flush()

    next_seq = db.query(DoctorProfile).count() + 1
    doc_code = f"DOC-{next_seq:04d}"
    while db.query(DoctorProfile).filter(DoctorProfile.doctor_code == doc_code).first():
        next_seq += 1
        doc_code = f"DOC-{next_seq:04d}"

    doc = DoctorProfile(
        user_id=user.id,
        doctor_code=doc_code,
        full_name=payload.full_name.strip(),
        title=payload.title,
        specialization=payload.specialization,
        qualification=payload.qualification,
        license_number=payload.license_number,
        bio=payload.bio,
        consultation_fee=payload.consultation_fee,
        slot_duration_minutes=payload.slot_duration_minutes,
        is_active=True,
        is_public=payload.is_public,
    )
    db.add(doc)
    db.flush()

    for day_idx in range(7):
        db.add(
            DoctorSchedule(
                doctor_id=doc.id,
                day_of_week=day_idx,
                start_time=time(16, 0),
                end_time=time(22, 0),
                slot_duration_minutes=payload.slot_duration_minutes,
                is_available=(day_idx < 6),
            )
        )

    log_audit_event(
        db=db,
        action="ADMIN_CREATED_DOCTOR",
        resource_type="doctor_profile",
        actor=current_user,
        resource_id=doc.id,
        request=request,
        details={"doctor_code": doc_code, "email": email_norm},
    )
    db.commit()
    db.refresh(doc)
    return _serialize_doctor(doc)


@router.put("/{doctor_id}")
def update_doctor_profile(
    doctor_id: int,
    payload: DoctorUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_DOCTOR)),
):
    doc = db.query(DoctorProfile).filter(DoctorProfile.id == doctor_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found.")

    role_name = current_user.role.name if current_user.role else ""
    if role_name == ROLE_DOCTOR and doc.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit another doctor's profile.")

    updates = payload.model_dump(exclude_unset=True)
    if "is_active" in updates and role_name != ROLE_ADMIN:
        updates.pop("is_active")

    for k, v in updates.items():
        if hasattr(doc, k) and v is not None:
            setattr(doc, k, v)
    if "full_name" in updates and updates["full_name"] and doc.user:
        doc.user.full_name = updates["full_name"]
    if "phone" in updates and updates["phone"] and doc.user:
        doc.user.phone = updates["phone"]
    if "is_active" in updates and updates["is_active"] is not None and doc.user:
        doc.user.is_active = updates["is_active"]
        if not updates["is_active"]:
            doc.user.token_version += 1

    log_audit_event(
        db=db,
        action="DOCTOR_PROFILE_UPDATED",
        resource_type="doctor_profile",
        actor=current_user,
        resource_id=doc.id,
        request=request,
        details=updates,
    )
    db.commit()
    db.refresh(doc)
    return _serialize_doctor(doc)


@router.put("/{doctor_id}/schedules")
def update_doctor_schedules(
    doctor_id: int,
    schedules: List[DoctorScheduleItemInput],
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_DOCTOR)),
):
    doc = db.query(DoctorProfile).filter(DoctorProfile.id == doctor_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found.")
    if current_user.role.name == ROLE_DOCTOR and doc.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify another doctor's schedule.")

    for item in schedules:
        st_parts = [int(x) for x in item.start_time.split(":")]
        et_parts = [int(x) for x in item.end_time.split(":")]
        sched = (
            db.query(DoctorSchedule)
            .filter(DoctorSchedule.doctor_id == doc.id, DoctorSchedule.day_of_week == item.day_of_week)
            .first()
        )
        if not sched:
            sched = DoctorSchedule(doctor_id=doc.id, day_of_week=item.day_of_week)
            db.add(sched)
        sched.start_time = time(st_parts[0], st_parts[1])
        sched.end_time = time(et_parts[0], et_parts[1])
        sched.slot_duration_minutes = item.slot_duration_minutes
        sched.is_available = item.is_available

    log_audit_event(
        db=db,
        action="DOCTOR_SCHEDULE_UPDATED",
        resource_type="doctor_schedule",
        actor=current_user,
        resource_id=doc.id,
        request=request,
    )
    db.commit()
    db.refresh(doc)
    return _serialize_doctor(doc)
