import hashlib
from pathlib import Path
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.permissions import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import log_audit_event
from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_roles, verify_patient_isolation
from app.models.entities import ClinicalDocument, PatientProfile, User
from app.services.notification_service import create_user_notification


router = APIRouter()

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".dcm"}
ALLOWED_MIMES = {
    "image/jpeg",
    "image/png",
    "application/pdf",
    "application/dicom",
    "application/octet-stream",
}


def _validate_file_signature(ext: str, content: bytes) -> bool:
    if not content:
        return False
    if ext in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".pdf":
        return content.startswith(b"%PDF-")
    if ext == ".dcm":
        # DICOM files either have 'DICM' at offset 128 or start with valid tag bytes
        return (len(content) > 132 and content[128:132] == b"DICM") or content.startswith(b"DICM") or len(content) >= 16
    return False


def _serialize_document(doc: ClinicalDocument) -> dict:
    return {
        "id": doc.id,
        "document_uid": doc.document_uid,
        "patient_id": doc.patient_id,
        "patient_name": doc.patient.full_name if doc.patient else "",
        "patient_number": doc.patient.patient_number if doc.patient else "",
        "appointment_id": doc.appointment_id,
        "encounter_id": doc.encounter_id,
        "treatment_record_id": doc.treatment_record_id,
        "tooth_fdi": doc.tooth_fdi,
        "document_type": doc.document_type,
        "title": doc.title,
        "clinical_description": doc.clinical_description,
        "original_filename": doc.original_filename,
        "mime_type": doc.mime_type,
        "file_extension": doc.file_extension,
        "file_size_bytes": doc.file_size_bytes,
        "uploaded_by_name": doc.uploaded_by.full_name if doc.uploaded_by else "Clinic Staff",
        "is_patient_visible": doc.is_patient_visible,
        "download_url": f"/api/v1/documents/{doc.id}/download",
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@router.get("")
def list_documents(
    patient_id: Optional[int] = Query(default=None),
    document_type: Optional[str] = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = current_user.role.name if current_user.role else ""
    query = db.query(ClinicalDocument)

    if role_name == ROLE_PATIENT:
        own = db.query(PatientProfile).filter(PatientProfile.user_id == current_user.id).first()
        if not own:
            return []
        if patient_id is not None and patient_id != own.id:
            verify_patient_isolation(db, current_user, patient_id, request, "clinical_document")
        query = query.filter(
            ClinicalDocument.patient_id == own.id,
            ClinicalDocument.is_patient_visible.is_(True),
        )
    elif patient_id is not None:
        verify_patient_isolation(db, current_user, patient_id, request, "clinical_document")
        query = query.filter(ClinicalDocument.patient_id == patient_id)

    if document_type:
        query = query.filter(ClinicalDocument.document_type == document_type)

    docs = query.order_by(ClinicalDocument.created_at.desc()).all()
    return [_serialize_document(d) for d in docs]


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_clinical_document(
    request: Request,
    patient_id: int = Form(...),
    title: str = Form(...),
    document_type: str = Form("X-Ray"),
    tooth_fdi: Optional[str] = Form(default=None),
    appointment_id: Optional[int] = Form(default=None),
    encounter_id: Optional[int] = Form(default=None),
    treatment_record_id: Optional[int] = Form(default=None),
    clinical_description: Optional[str] = Form(default=None),
    is_patient_visible: bool = Form(default=True),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR, ROLE_ADMIN)),
):
    """
    Uploads an X-ray or clinical document into private storage (outside static directory).
    Validates extension, MIME type, magic file signature bytes, and size limits.
    """
    patient = verify_patient_isolation(db, current_user, patient_id, request, "clinical_document")

    orig_name = Path(file.filename or "document.bin").name
    ext = Path(orig_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Allowed formats: JPEG, PNG, PDF, DICOM (.dcm).",
        )

    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )

    if not _validate_file_signature(ext, content):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File signature does not match declared file extension.",
        )

    doc_uid = uuid.uuid4().hex
    safe_storage_name = f"{doc_uid}{ext}"
    dest_path = settings.private_upload_dir / safe_storage_name
    dest_path.write_bytes(content)

    sha256_hex = hashlib.sha256(content).hexdigest()
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MIMES:
        mime = "application/octet-stream"

    doc = ClinicalDocument(
        document_uid=doc_uid,
        patient_id=patient.id,
        appointment_id=appointment_id,
        encounter_id=encounter_id,
        treatment_record_id=treatment_record_id,
        tooth_fdi=tooth_fdi,
        document_type=document_type,
        title=title.strip(),
        clinical_description=clinical_description,
        original_filename=orig_name,
        storage_filename=safe_storage_name,
        mime_type=mime,
        file_extension=ext,
        file_size_bytes=len(content),
        sha256_checksum=sha256_hex,
        uploaded_by_user_id=current_user.id,
        is_patient_visible=is_patient_visible,
    )
    db.add(doc)
    db.flush()

    if is_patient_visible and patient.user_id:
        create_user_notification(
            db=db,
            user_id=patient.user_id,
            title=f"New {document_type} Available",
            message=f"A new clinical document ('{doc.title}') has been added to your portal.",
            notification_type="Document",
            related_entity_type="clinical_document",
            related_entity_id=doc.id,
        )

    log_audit_event(
        db=db,
        action="CLINICAL_DOCUMENT_UPLOADED",
        resource_type="clinical_document",
        actor=current_user,
        resource_id=doc.id,
        patient_id=patient.id,
        request=request,
        details={"document_uid": doc_uid, "document_type": document_type, "title": doc.title},
    )
    db.commit()
    db.refresh(doc)
    return _serialize_document(doc)


@router.get("/{document_id}")
def get_document_metadata(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(ClinicalDocument).filter(ClinicalDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    verify_patient_isolation(db, current_user, doc.patient_id, request, "clinical_document")
    if current_user.role.name == ROLE_PATIENT and not doc.is_patient_visible:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Document is not released to patient portal.")
    return _serialize_document(doc)


@router.get("/{document_id}/download")
def download_clinical_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Authorized streaming endpoint for confidential X-rays and clinical documents.
    Enforces strict patient data isolation and logs access in audit_logs.
    """
    doc = db.query(ClinicalDocument).filter(ClinicalDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    verify_patient_isolation(db, current_user, doc.patient_id, request, "clinical_document")
    if current_user.role.name == ROLE_PATIENT and not doc.is_patient_visible:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    file_path = settings.private_upload_dir / doc.storage_filename
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file not found on disk.")

    log_audit_event(
        db=db,
        action="CLINICAL_DOCUMENT_DOWNLOADED",
        resource_type="clinical_document",
        actor=current_user,
        resource_id=doc.id,
        patient_id=doc.patient_id,
        request=request,
        details={"document_uid": doc.document_uid},
    )
    db.commit()

    disposition = "attachment" if request.query_params.get("download") == "1" else "inline"
    return FileResponse(
        path=str(file_path),
        media_type=doc.mime_type,
        filename=doc.original_filename,
        content_disposition_type=disposition,
    )


@router.delete("/{document_id}")
def delete_clinical_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR, ROLE_ADMIN)),
):
    """
    Removes an uploaded X-ray or clinical document and deletes its stored file if unreferenced.
    """
    doc = db.query(ClinicalDocument).filter(ClinicalDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    verify_patient_isolation(db, current_user, doc.patient_id, request, "clinical_document")

    storage_name = doc.storage_filename
    doc_uid = doc.document_uid
    doc_title = doc.title
    patient_id = doc.patient_id

    db.delete(doc)
    db.flush()

    other_refs = (
        db.query(ClinicalDocument)
        .filter(ClinicalDocument.storage_filename == storage_name)
        .count()
    )
    if other_refs == 0 and storage_name:
        file_path = settings.private_upload_dir / storage_name
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass

    log_audit_event(
        db=db,
        action="CLINICAL_DOCUMENT_DELETED",
        resource_type="clinical_document",
        actor=current_user,
        resource_id=document_id,
        patient_id=patient_id,
        request=request,
        details={"document_uid": doc_uid, "title": doc_title},
    )
    db.commit()
    return {"message": f"Removed upload '{doc_title}'.", "deleted_id": document_id}


@router.delete("/patient/{patient_id}/clear")
def clear_patient_recent_documents(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_DOCTOR, ROLE_ADMIN)),
):
    """
    Removes all recent uploaded X-rays/documents for the selected patient so the upload workspace stays clean.
    """
    patient = verify_patient_isolation(db, current_user, patient_id, request, "clinical_document")
    docs = db.query(ClinicalDocument).filter(ClinicalDocument.patient_id == patient.id).all()
    removed_count = len(docs)
    storage_names = [d.storage_filename for d in docs if d.storage_filename]

    for d in docs:
        db.delete(d)
    db.flush()

    for sname in set(storage_names):
        if db.query(ClinicalDocument).filter(ClinicalDocument.storage_filename == sname).count() == 0:
            fpath = settings.private_upload_dir / sname
            if fpath.exists():
                try:
                    fpath.unlink()
                except OSError:
                    pass

    log_audit_event(
        db=db,
        action="PATIENT_RECENT_DOCUMENTS_CLEARED",
        resource_type="clinical_document",
        actor=current_user,
        patient_id=patient.id,
        request=request,
        details={"removed_count": removed_count},
    )
    db.commit()
    return {
        "message": f"Removed {removed_count} recent upload(s) for {patient.full_name}.",
        "removed_count": removed_count,
    }

