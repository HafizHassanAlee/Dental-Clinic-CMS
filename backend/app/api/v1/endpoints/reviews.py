from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from app.core.permissions import ROLE_ADMIN, ROLE_PATIENT
from app.core.security import log_audit_event
from app.db.session import get_db
from app.dependencies.auth import (
    get_current_patient_profile,
    require_roles,
)
from app.models.entities import PatientProfile, Review, User
from app.schemas.domain import ReviewModerationRequest, ReviewSubmitRequest


router = APIRouter()


def _serialize_public_review(r: Review) -> dict:
    """Public representation: never exposes private user_id, patient_id, phone, or medical details."""
    return {
        "id": r.id,
        "reviewer_display_name": r.reviewer_display_name,
        "rating": r.rating,
        "title": r.title,
        "comment": r.comment,
        "source_label": r.source_label,
        "created_at": r.created_at.strftime("%B %Y") if r.created_at else "",
    }


def _serialize_patient_review(r: Review) -> dict:
    return {
        "id": r.id,
        "reviewer_display_name": r.reviewer_display_name,
        "rating": r.rating,
        "title": r.title,
        "comment": r.comment,
        "status": r.status,
        "consent_to_publish": r.consent_to_publish,
        "is_deletion_requested": r.is_deletion_requested,
        "moderation_reason": r.moderation_reason,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/public")
def list_public_approved_reviews(db: Session = Depends(get_db)):
    reviews = (
        db.query(Review)
        .filter(
            Review.status == "Approved",
            Review.consent_to_publish.is_(True),
            Review.is_deletion_requested.is_(False),
        )
        .order_by(Review.id.asc())
        .all()
    )
    return [_serialize_public_review(r) for r in reviews]


@router.get("/my")
def list_my_reviews(
    db: Session = Depends(get_db),
    patient: PatientProfile = Depends(get_current_patient_profile),
):
    reviews = (
        db.query(Review)
        .filter(Review.patient_id == patient.id)
        .order_by(Review.created_at.desc())
        .all()
    )
    return [_serialize_patient_review(r) for r in reviews]


@router.post("", status_code=status.HTTP_201_CREATED)
def submit_patient_review(
    payload: ReviewSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_PATIENT)),
    patient: PatientProfile = Depends(get_current_patient_profile),
):
    display_name = (payload.reviewer_display_name or patient.full_name).strip()
    rev = Review(
        patient_id=patient.id,
        user_id=current_user.id,
        reviewer_display_name=display_name,
        rating=payload.rating,
        title=payload.title,
        comment=payload.comment.strip(),
        status="Pending",
        consent_to_publish=payload.consent_to_publish,
        source_label="Verified Clinic Patient",
    )
    db.add(rev)
    log_audit_event(
        db=db,
        action="PATIENT_REVIEW_SUBMITTED",
        resource_type="review",
        actor=current_user,
        patient_id=patient.id,
        request=request,
        details={"rating": payload.rating, "status": "Pending"},
    )
    db.commit()
    db.refresh(rev)
    return _serialize_patient_review(rev)


@router.put("/{review_id}")
def update_my_review(
    review_id: int,
    payload: ReviewSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_PATIENT)),
    patient: PatientProfile = Depends(get_current_patient_profile),
):
    rev = db.query(Review).filter(Review.id == review_id).first()
    if not rev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")
    if rev.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own submitted reviews.",
        )

    rev.rating = payload.rating
    rev.title = payload.title
    rev.comment = payload.comment.strip()
    rev.consent_to_publish = payload.consent_to_publish
    rev.status = "Pending"

    log_audit_event(
        db=db,
        action="PATIENT_REVIEW_EDITED",
        resource_type="review",
        actor=current_user,
        resource_id=rev.id,
        patient_id=patient.id,
        request=request,
    )
    db.commit()
    db.refresh(rev)
    return _serialize_patient_review(rev)


@router.delete("/{review_id}")
def request_review_deletion(
    review_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_PATIENT)),
    patient: PatientProfile = Depends(get_current_patient_profile),
):
    rev = db.query(Review).filter(Review.id == review_id).first()
    if not rev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")
    if rev.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only remove your own reviews.",
        )

    rev.is_deletion_requested = True
    rev.status = "Hidden"
    log_audit_event(
        db=db,
        action="PATIENT_REVIEW_REMOVAL_REQUESTED",
        resource_type="review",
        actor=current_user,
        resource_id=rev.id,
        patient_id=patient.id,
        request=request,
    )
    db.commit()
    return {"message": "Your review has been unpublished and marked for removal."}


@router.get("/admin")
def admin_list_reviews(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    rating: Optional[int] = Query(default=None, ge=1, le=5),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    query = db.query(Review)
    if status_filter:
        query = query.filter(Review.status == status_filter)
    if rating:
        query = query.filter(Review.rating == rating)
    items = query.order_by(Review.created_at.desc()).all()
    return [
        {
            **_serialize_patient_review(r),
            "patient_id": r.patient_id,
            "user_id": r.user_id,
            "moderated_at": r.moderated_at.isoformat() if r.moderated_at else None,
        }
        for r in items
    ]


@router.patch("/{review_id}/moderate")
def moderate_review(
    review_id: int,
    payload: ReviewModerationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    rev = db.query(Review).filter(Review.id == review_id).first()
    if not rev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")

    if payload.status == "Approved" and not rev.consent_to_publish:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot publish a review without the patient's explicit consent_to_publish.",
        )

    rev.status = payload.status
    rev.moderation_reason = payload.moderation_reason
    rev.moderated_by_user_id = current_user.id
    rev.moderated_at = datetime.now(timezone.utc)

    log_audit_event(
        db=db,
        action=f"REVIEW_MODERATED_{payload.status.upper()}",
        resource_type="review",
        actor=current_user,
        resource_id=rev.id,
        patient_id=rev.patient_id,
        request=request,
        details={"status": payload.status, "reason": payload.moderation_reason},
    )
    db.commit()
    db.refresh(rev)
    return _serialize_patient_review(rev)
