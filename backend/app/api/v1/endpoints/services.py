import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from app.core.permissions import ROLE_ADMIN
from app.core.security import log_audit_event
from app.db.session import get_db
from app.dependencies.auth import require_roles
from app.models.entities import Service, User
from app.schemas.domain import ServiceCreateUpdate, ServiceUpdateRequest


router = APIRouter()


def _serialize_service(s: Service) -> dict:
    return {
        "id": s.id,
        "code": s.code,
        "slug": s.slug,
        "name": s.name,
        "category": s.category,
        "tagline": s.tagline,
        "short_description": s.short_description,
        "detailed_description": s.detailed_description,
        "price": float(s.price),
        "currency": "PKR",
        "duration_minutes": s.duration_minutes,
        "icon_name": s.icon_name,
        "is_published": s.is_published,
        "is_bookable": s.is_bookable,
        "display_order": s.display_order,
    }


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


@router.get("")
def list_services(
    published_only: bool = Query(default=True),
    category: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Service)
    if published_only:
        query = query.filter(Service.is_published.is_(True))
    if category:
        query = query.filter(Service.category == category)
    items = query.order_by(Service.display_order.asc(), Service.id.asc()).all()
    return [_serialize_service(s) for s in items]


@router.get("/{service_id_or_slug}")
def get_service(service_id_or_slug: str, db: Session = Depends(get_db)):
    if service_id_or_slug.isdigit():
        s = db.query(Service).filter(Service.id == int(service_id_or_slug)).first()
    else:
        s = db.query(Service).filter(Service.slug == service_id_or_slug).first()
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found.")
    return _serialize_service(s)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    if db.query(Service).filter(Service.code == payload.code.strip()).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Service code already exists.")

    slug = _slugify(payload.name)
    if db.query(Service).filter(Service.slug == slug).first():
        slug = f"{slug}-{payload.code.strip().lower()}"

    srv = Service(
        code=payload.code.strip(),
        slug=slug,
        name=payload.name.strip(),
        category=payload.category.strip(),
        tagline=payload.tagline,
        short_description=payload.short_description.strip(),
        detailed_description=payload.detailed_description,
        price=payload.price,
        duration_minutes=payload.duration_minutes,
        icon_name=payload.icon_name,
        is_published=payload.is_published,
        is_bookable=payload.is_bookable,
        display_order=payload.display_order,
    )
    db.add(srv)
    log_audit_event(
        db=db,
        action="SERVICE_CREATED",
        resource_type="service",
        actor=current_user,
        request=request,
        details={"code": srv.code, "name": srv.name, "price": str(srv.price)},
    )
    db.commit()
    db.refresh(srv)
    return _serialize_service(srv)


@router.put("/{service_id}")
def update_service(
    service_id: int,
    payload: ServiceUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Updates catalog service metadata/pricing without altering historical InvoiceLineItem records."""
    srv = db.query(Service).filter(Service.id == service_id).first()
    if not srv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found.")

    old_price = srv.price
    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        if isinstance(val, str) and field in {"code", "name", "category", "short_description"}:
            val = val.strip()
        setattr(srv, field, val)

    log_audit_event(
        db=db,
        action="SERVICE_UPDATED",
        resource_type="service",
        actor=current_user,
        resource_id=srv.id,
        request=request,
        details={"old_price": str(old_price), "new_price": str(srv.price), "updated_fields": list(update_data.keys())},
    )
    db.commit()
    db.refresh(srv)
    return _serialize_service(srv)
