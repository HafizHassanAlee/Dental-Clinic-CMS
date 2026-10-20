from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from app.core.permissions import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import log_audit_event
from app.db.session import get_db
from app.dependencies.auth import get_current_user, verify_patient_isolation
from app.models.entities import (
    Appointment,
    DoctorProfile,
    DoctorSchedule,
    PatientProfile,
    Service,
    User,
)
from app.schemas.domain import (
    AppointmentCreateRequest,
    AppointmentRescheduleRequest,
    AppointmentStatusUpdateRequest,
)
from app.services.notification_service import create_user_notification


router = APIRouter()

ACTIVE_CONFLICT_STATUSES = {"Requested", "Confirmed", "CheckedIn", "InProgress"}
ALLOWED_STATUSES = {"Requested", "Confirmed", "CheckedIn", "InProgress", "Completed", "Cancelled", "NoShow"}


def _parse_hhmm(val: str) -> time:
    parts = [int(p) for p in val.strip().split(":")]
    return time(parts[0], parts[1])


def _add_minutes(t: time, minutes: int) -> time:
    dt = datetime.combine(date.today(), t) + timedelta(minutes=minutes)
    return dt.time()


def _serialize_appointment(a: Appointment) -> dict:
    return {
        "id": a.id,
        "appointment_number": a.appointment_number,
        "patient_id": a.patient_id,
        "patient_name": a.patient.full_name if a.patient else "",
        "patient_number": a.patient.patient_number if a.patient else "",
        "patient_phone": a.patient.phone if a.patient else "",
        "doctor_id": a.doctor_id,
        "doctor_name": a.doctor.full_name if a.doctor else "Dr. Aisha Salman",
        "service_id": a.service_id,
        "service_name": a.service.name if a.service else "Dental Consultation",
        "appointment_date": a.appointment_date.isoformat(),
        "start_time": a.start_time.strftime("%H:%M"),
        "end_time": a.end_time.strftime("%H:%M"),
        "status": a.status,
        "reason_for_visit": a.reason_for_visit,
        "patient_notes": a.patient_notes,
        "clinical_status_notes": a.clinical_status_notes,
        "cancellation_reason": a.cancellation_reason,
        "follow_up_recommended_date": a.follow_up_recommended_date.isoformat()
        if a.follow_up_recommended_date
        else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _check_slot_conflict(
    db: Session,
    doctor_id: int,
    appointment_date: date,
    start_t: time,
    end_t: time,
    exclude_appointment_id: Optional[int] = None,
) -> Optional[Appointment]:
    query = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appointment_date,
        Appointment.status.in_(ACTIVE_CONFLICT_STATUSES),
        Appointment.start_time < end_t,
        Appointment.end_time > start_t,
    )
    if exclude_appointment_id is not None:
        query = query.filter(Appointment.id != exclude_appointment_id)
    return query.first()


@router.get("/available-slots")
def get_available_slots(
    doctor_id: int = Query(...),
    appointment_date: date = Query(...),
    service_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    doc = db.query(DoctorProfile).filter(DoctorProfile.id == doctor_id, DoctorProfile.is_active.is_(True)).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found.")

    day_of_week = appointment_date.weekday()
    sched = (
        db.query(DoctorSchedule)
        .filter(DoctorSchedule.doctor_id == doc.id, DoctorSchedule.day_of_week == day_of_week)
        .first()
    )

    if sched and not sched.is_available:
        return {"doctor_id": doctor_id, "appointment_date": appointment_date.isoformat(), "slots": []}

    start_window = sched.start_time if sched else time(16, 0)
    end_window = sched.end_time if sched else time(22, 0)
    slot_mins = sched.slot_duration_minutes if sched else doc.slot_duration_minutes or 30
    if service_id:
        srv = db.query(Service).filter(Service.id == service_id).first()
        if srv and srv.duration_minutes:
            slot_mins = srv.duration_minutes

    existing = (
        db.query(Appointment)
        .filter(
            Appointment.doctor_id == doc.id,
            Appointment.appointment_date == appointment_date,
            Appointment.status.in_(ACTIVE_CONFLICT_STATUSES),
        )
        .all()
    )

    slots = []
    cur_dt = datetime.combine(appointment_date, start_window)
    end_dt = datetime.combine(appointment_date, end_window)
    while cur_dt + timedelta(minutes=slot_mins) <= end_dt:
        s_t = cur_dt.time()
        e_t = (cur_dt + timedelta(minutes=slot_mins)).time()
        busy = any(a.start_time < e_t and a.end_time > s_t for a in existing)
        slots.append(
            {
                "start_time": s_t.strftime("%H:%M"),
                "end_time": e_t.strftime("%H:%M"),
                "is_available": not busy,
            }
        )
        cur_dt += timedelta(minutes=30)

    return {
        "doctor_id": doctor_id,
        "appointment_date": appointment_date.isoformat(),
        "opening_hours": f"{start_window.strftime('%H:%M')} - {end_window.strftime('%H:%M')}",
        "slots": slots,
    }


@router.get("")
def list_appointments(
    appointment_date: Optional[date] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    doctor_id: Optional[int] = Query(default=None),
    patient_id: Optional[int] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = current_user.role.name if current_user.role else ""
    query = db.query(Appointment)

    if role_name == ROLE_PATIENT:
        own_profile = db.query(PatientProfile).filter(PatientProfile.user_id == current_user.id).first()
        if not own_profile:
            return []
        if patient_id is not None and patient_id != own_profile.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You cannot query another patient's appointments.",
            )
        query = query.filter(Appointment.patient_id == own_profile.id)
    else:
        if patient_id is not None:
            query = query.filter(Appointment.patient_id == patient_id)
        if doctor_id is not None:
            query = query.filter(Appointment.doctor_id == doctor_id)

    if appointment_date is not None:
        query = query.filter(Appointment.appointment_date == appointment_date)
    if date_from is not None:
        query = query.filter(Appointment.appointment_date >= date_from)
    if date_to is not None:
        query = query.filter(Appointment.appointment_date <= date_to)
    if status_filter:
        query = query.filter(Appointment.status == status_filter)

    items = query.order_by(Appointment.appointment_date.desc(), Appointment.start_time.asc()).all()
    return [_serialize_appointment(a) for a in items]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = current_user.role.name if current_user.role else ""
    if payload.appointment_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Appointment date cannot be in the past.",
        )

    if role_name == ROLE_PATIENT:
        patient = db.query(PatientProfile).filter(PatientProfile.user_id == current_user.id).first()
        if not patient:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Patient profile not found.")
        if payload.patient_id and payload.patient_id != patient.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Patients can only book appointments for their own account.",
            )
        target_patient_id = patient.id
        initial_status = "Confirmed"
    else:
        if not payload.patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="patient_id is required when staff schedules an appointment.",
            )
        patient = db.query(PatientProfile).filter(PatientProfile.id == payload.patient_id).first()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
        target_patient_id = patient.id
        initial_status = "Confirmed"

    doctor = (
        db.query(DoctorProfile)
        .filter(DoctorProfile.id == payload.doctor_id, DoctorProfile.is_active.is_(True))
        .first()
    )
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Selected doctor is not available.")

    duration = doctor.slot_duration_minutes or 30
    if payload.service_id:
        srv = db.query(Service).filter(Service.id == payload.service_id).first()
        if not srv or not srv.is_bookable:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected service is not bookable.")
        duration = srv.duration_minutes or duration

    start_t = _parse_hhmm(payload.start_time)
    end_t = _add_minutes(start_t, duration)

    conflict = _check_slot_conflict(db, doctor.id, payload.appointment_date, start_t, end_t)
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Time slot conflict: {doctor.full_name} already has a scheduled appointment "
                f"({conflict.start_time.strftime('%H:%M')} - {conflict.end_time.strftime('%H:%M')}) on {payload.appointment_date.isoformat()}."
            ),
        )

    year = datetime.now(timezone.utc).year
    next_seq = db.query(Appointment).count() + 1
    apt_num = f"APT-{year}-{next_seq:05d}"
    while db.query(Appointment).filter(Appointment.appointment_number == apt_num).first():
        next_seq += 1
        apt_num = f"APT-{year}-{next_seq:05d}"

    apt = Appointment(
        appointment_number=apt_num,
        patient_id=target_patient_id,
        doctor_id=doctor.id,
        service_id=payload.service_id,
        appointment_date=payload.appointment_date,
        start_time=start_t,
        end_time=end_t,
        status=initial_status,
        reason_for_visit=payload.reason_for_visit.strip(),
        patient_notes=payload.patient_notes,
        created_by_user_id=current_user.id,
    )
    db.add(apt)
    db.flush()

    create_user_notification(
        db=db,
        user_id=patient.user_id,
        title=f"Appointment {apt_num} {initial_status}",
        message=f"Appointment with {doctor.full_name} on {apt.appointment_date.isoformat()} at {start_t.strftime('%H:%M')} is {initial_status.lower()}.",
        notification_type="Appointment",
        related_entity_type="appointment",
        related_entity_id=apt.id,
    )

    log_audit_event(
        db=db,
        action="APPOINTMENT_BOOKED",
        resource_type="appointment",
        actor=current_user,
        resource_id=apt.id,
        patient_id=target_patient_id,
        request=request,
        details={"appointment_number": apt_num, "date": apt.appointment_date.isoformat(), "time": payload.start_time},
    )
    db.commit()
    db.refresh(apt)
    return _serialize_appointment(apt)


@router.get("/{appointment_id}")
def get_appointment(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    apt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not apt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found.")

    verify_patient_isolation(db, current_user, apt.patient_id, request, "appointment")
    return _serialize_appointment(apt)


@router.patch("/{appointment_id}/status")
def update_appointment_status(
    appointment_id: int,
    payload: AppointmentStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    apt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not apt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found.")

    verify_patient_isolation(db, current_user, apt.patient_id, request, "appointment")

    role_name = current_user.role.name if current_user.role else ""
    new_status = payload.status.strip()
    if new_status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status '{new_status}'.")

    if role_name == ROLE_PATIENT and new_status != "Cancelled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patients may only request appointment cancellation.",
        )

    if new_status == "Confirmed":
        conflict = _check_slot_conflict(
            db, apt.doctor_id, apt.appointment_date, apt.start_time, apt.end_time, exclude_appointment_id=apt.id
        )
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot confirm appointment: conflicting appointment exists in this slot.",
            )

    now = datetime.now(timezone.utc)
    apt.status = new_status
    if new_status == "CheckedIn":
        apt.checked_in_at = now
    elif new_status == "Completed":
        apt.completed_at = now
    elif new_status == "Cancelled":
        apt.cancellation_reason = payload.cancellation_reason or "Cancelled by user"

    if payload.clinical_status_notes is not None:
        apt.clinical_status_notes = payload.clinical_status_notes
    if payload.follow_up_recommended_date is not None:
        apt.follow_up_recommended_date = payload.follow_up_recommended_date

    if apt.patient and apt.patient.user_id:
        create_user_notification(
            db=db,
            user_id=apt.patient.user_id,
            title=f"Appointment {apt.appointment_number} Updated",
            message=f"Your appointment on {apt.appointment_date.isoformat()} is now marked as {new_status}.",
            notification_type="Appointment",
            related_entity_type="appointment",
            related_entity_id=apt.id,
        )

    log_audit_event(
        db=db,
        action=f"APPOINTMENT_STATUS_{new_status.upper()}",
        resource_type="appointment",
        actor=current_user,
        resource_id=apt.id,
        patient_id=apt.patient_id,
        request=request,
        details={"status": new_status},
    )
    db.commit()
    db.refresh(apt)
    return _serialize_appointment(apt)


@router.post("/{appointment_id}/reschedule")
def reschedule_appointment(
    appointment_id: int,
    payload: AppointmentRescheduleRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    apt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not apt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found.")

    verify_patient_isolation(db, current_user, apt.patient_id, request, "appointment")

    if payload.appointment_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reschedule an appointment to a past date.",
        )

    target_doc_id = payload.doctor_id or apt.doctor_id
    duration = 30
    if apt.service and apt.service.duration_minutes:
        duration = apt.service.duration_minutes
    start_t = _parse_hhmm(payload.start_time)
    end_t = _add_minutes(start_t, duration)

    conflict = _check_slot_conflict(
        db, target_doc_id, payload.appointment_date, start_t, end_t, exclude_appointment_id=apt.id
    )
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Selected reschedule slot conflicts with an existing appointment.",
        )

    old_date = apt.appointment_date.isoformat()
    old_time = apt.start_time.strftime("%H:%M")
    apt.doctor_id = target_doc_id
    apt.appointment_date = payload.appointment_date
    apt.start_time = start_t
    apt.end_time = end_t
    if apt.status == "Cancelled":
        apt.status = "Confirmed"

    if apt.patient and apt.patient.user_id:
        create_user_notification(
            db=db,
            user_id=apt.patient.user_id,
            title=f"Appointment {apt.appointment_number} Rescheduled",
            message=f"Moved from {old_date} {old_time} to {apt.appointment_date.isoformat()} {start_t.strftime('%H:%M')}.",
            notification_type="Appointment",
            related_entity_type="appointment",
            related_entity_id=apt.id,
        )

    log_audit_event(
        db=db,
        action="APPOINTMENT_RESCHEDULED",
        resource_type="appointment",
        actor=current_user,
        resource_id=apt.id,
        patient_id=apt.patient_id,
        request=request,
        details={"old_date": old_date, "new_date": apt.appointment_date.isoformat(), "new_time": payload.start_time},
    )
    db.commit()
    db.refresh(apt)
    return _serialize_appointment(apt)
