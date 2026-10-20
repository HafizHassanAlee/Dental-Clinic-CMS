import csv
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session
from app.core.permissions import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import log_audit_event
from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_roles, verify_patient_isolation
from app.models.entities import (
    ClinicSetting,
    Invoice,
    InvoiceLineItem,
    PatientProfile,
    Payment,
    Receipt,
    User,
)
from app.schemas.domain import (
    InvoiceCreateRequest,
    PaymentRecordRequest,
    PaymentReverseRequest,
)
from app.services.notification_service import create_user_notification
from app.services.pdf_service import generate_invoice_pdf, generate_receipt_pdf


invoices_router = APIRouter()
payments_router = APIRouter()
receipts_router = APIRouter()

TWOPLACES = Decimal("0.01")


def _d(val: Decimal | float | int | str) -> Decimal:
    return Decimal(str(val)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _recalculate_invoice_totals(inv: Invoice) -> None:
    recorded_sum = sum(
        (_d(p.amount) for p in inv.payments if p.status == "Recorded"),
        Decimal("0.00"),
    )
    inv.amount_paid = recorded_sum
    rem = _d(inv.total_amount) - recorded_sum
    inv.balance_due = max(Decimal("0.00"), rem)

    if inv.document_kind == "Estimate":
        inv.status = "Estimate"
    elif inv.status == "Voided":
        pass
    elif inv.balance_due == Decimal("0.00") and inv.total_amount > Decimal("0.00"):
        inv.status = "Paid"
    elif inv.amount_paid > Decimal("0.00"):
        inv.status = "PartiallyPaid"
    else:
        inv.status = "Unpaid"


def _serialize_invoice(inv: Invoice) -> dict:
    return {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "patient_id": inv.patient_id,
        "patient_name": inv.patient.full_name if inv.patient else "",
        "patient_number": inv.patient.patient_number if inv.patient else "",
        "appointment_id": inv.appointment_id,
        "encounter_id": inv.encounter_id,
        "document_kind": inv.document_kind,
        "issue_date": inv.issue_date.isoformat(),
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "currency": inv.currency,
        "subtotal": float(inv.subtotal),
        "discount_amount": float(inv.discount_amount),
        "discount_reason": inv.discount_reason,
        "tax_amount": float(inv.tax_amount),
        "total_amount": float(inv.total_amount),
        "amount_paid": float(inv.amount_paid),
        "balance_due": float(inv.balance_due),
        "status": inv.status,
        "notes": inv.notes,
        "pdf_url": f"/api/v1/invoices/{inv.id}/pdf",
        "line_items": [
            {
                "id": li.id,
                "service_id": li.service_id,
                "tooth_fdi": li.tooth_fdi,
                "description": li.description,
                "quantity": li.quantity,
                "unit_price": float(li.unit_price),
                "line_total": float(li.line_total),
            }
            for li in inv.line_items
        ],
        "payments": [
            {
                "id": p.id,
                "payment_number": p.payment_number,
                "amount": float(p.amount),
                "payment_method": p.payment_method,
                "reference_number": p.reference_number,
                "status": p.status,
                "payment_date": p.payment_date.isoformat() if p.payment_date else None,
                "receipt_number": p.receipt.receipt_number if p.receipt else None,
                "receipt_id": p.receipt.id if p.receipt else None,
            }
            for p in inv.payments
        ],
    }


def _serialize_payment(p: Payment) -> dict:
    return {
        "id": p.id,
        "payment_number": p.payment_number,
        "invoice_id": p.invoice_id,
        "invoice_number": p.invoice.invoice_number if p.invoice else "",
        "patient_id": p.patient_id,
        "patient_name": p.patient.full_name if p.patient else "",
        "patient_number": p.patient.patient_number if p.patient else "",
        "amount": float(p.amount),
        "currency": p.currency,
        "payment_method": p.payment_method,
        "reference_number": p.reference_number,
        "status": p.status,
        "reversal_reason": p.reversal_reason,
        "payment_date": p.payment_date.isoformat() if p.payment_date else None,
        "receipt_id": p.receipt.id if p.receipt else None,
        "receipt_number": p.receipt.receipt_number if p.receipt else None,
    }


def _serialize_receipt(r: Receipt) -> dict:
    return {
        "id": r.id,
        "receipt_number": r.receipt_number,
        "payment_id": r.payment_id,
        "payment_number": r.payment.payment_number if r.payment else "",
        "invoice_id": r.invoice_id,
        "invoice_number": r.invoice.invoice_number if r.invoice else "",
        "patient_id": r.patient_id,
        "patient_name": r.patient.full_name if r.patient else "",
        "patient_number": r.patient.patient_number if r.patient else "",
        "amount_received": float(r.amount_received),
        "currency": r.currency,
        "payment_method": r.payment_method,
        "issued_at": r.issued_at.isoformat() if r.issued_at else None,
        "is_voided": r.is_voided,
        "notes": r.notes,
        "pdf_url": f"/api/v1/receipts/{r.id}/pdf",
    }


# ============================================================================
# INVOICES ROUTER (/api/v1/invoices)
# ============================================================================


@invoices_router.get("")
def list_invoices(
    patient_id: Optional[int] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = current_user.role.name if current_user.role else ""
    query = db.query(Invoice)

    if role_name == ROLE_PATIENT:
        own = db.query(PatientProfile).filter(PatientProfile.user_id == current_user.id).first()
        if not own:
            return []
        if patient_id is not None and patient_id != own.id:
            verify_patient_isolation(db, current_user, patient_id, request, "invoice")
        query = query.filter(Invoice.patient_id == own.id)
    elif patient_id is not None:
        verify_patient_isolation(db, current_user, patient_id, request, "invoice")
        query = query.filter(Invoice.patient_id == patient_id)

    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    if date_from:
        query = query.filter(Invoice.issue_date >= date_from)
    if date_to:
        query = query.filter(Invoice.issue_date <= date_to)

    items = query.order_by(Invoice.issue_date.desc(), Invoice.id.desc()).all()
    return [_serialize_invoice(i) for i in items]


@invoices_router.get("/{invoice_id}")
def get_invoice(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    verify_patient_isolation(db, current_user, inv.patient_id, request, "invoice")
    return _serialize_invoice(inv)


@invoices_router.post("", status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_DOCTOR)),
):
    """
    Creates an itemized Invoice or Estimate using server-side Decimal arithmetic in PKR.
    Never generates a payment receipt merely because an invoice was created.
    """
    patient = verify_patient_isolation(db, current_user, payload.patient_id, request, "invoice")

    subtotal = Decimal("0.00")
    line_entities = []
    for item in payload.items:
        unit_p = _d(item.unit_price)
        qty = int(item.quantity)
        line_tot = _d(unit_p * Decimal(qty))
        subtotal = _d(subtotal + line_tot)
        line_entities.append(
            InvoiceLineItem(
                service_id=item.service_id,
                tooth_fdi=item.tooth_fdi,
                description=item.description.strip(),
                quantity=qty,
                unit_price=unit_p,
                line_total=line_tot,
            )
        )

    discount = _d(payload.discount_amount)
    tax = _d(payload.tax_amount)
    if discount > subtotal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Discount amount cannot exceed invoice subtotal.",
        )

    total_amount = _d(subtotal - discount + tax)
    year = datetime.now(timezone.utc).year
    prefix = "EST" if payload.document_kind == "Estimate" else "INV"
    next_seq = db.query(Invoice).count() + 1
    inv_num = f"{prefix}-{year}-{next_seq:05d}"
    while db.query(Invoice).filter(Invoice.invoice_number == inv_num).first():
        next_seq += 1
        inv_num = f"{prefix}-{year}-{next_seq:05d}"

    init_status = "Estimate" if payload.document_kind == "Estimate" else "Unpaid"
    inv = Invoice(
        invoice_number=inv_num,
        patient_id=patient.id,
        appointment_id=payload.appointment_id,
        encounter_id=payload.encounter_id,
        document_kind=payload.document_kind,
        issue_date=date.today(),
        due_date=payload.due_date or date.today(),
        currency="PKR",
        subtotal=subtotal,
        discount_amount=discount,
        discount_reason=payload.discount_reason,
        tax_amount=tax,
        total_amount=total_amount,
        amount_paid=Decimal("0.00"),
        balance_due=total_amount if payload.document_kind == "Invoice" else Decimal("0.00"),
        status=init_status,
        notes=payload.notes,
        created_by_user_id=current_user.id,
    )
    db.add(inv)
    db.flush()

    for li in line_entities:
        li.invoice_id = inv.id
        db.add(li)

    if patient.user_id:
        create_user_notification(
            db=db,
            user_id=patient.user_id,
            title=f"New {payload.document_kind} Issued ({inv_num})",
            message=f"{payload.document_kind} {inv_num} for PKR {total_amount:,.2f} is now available in your portal.",
            notification_type="Billing",
            related_entity_type="invoice",
            related_entity_id=inv.id,
        )

    log_audit_event(
        db=db,
        action="INVOICE_CREATED",
        resource_type="invoice",
        actor=current_user,
        resource_id=inv.id,
        patient_id=patient.id,
        request=request,
        details={"invoice_number": inv_num, "total_amount": str(total_amount), "kind": payload.document_kind},
    )
    db.commit()
    db.refresh(inv)
    return _serialize_invoice(inv)


@invoices_router.get("/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    verify_patient_isolation(db, current_user, inv.patient_id, request, "invoice")
    clinic = db.query(ClinicSetting).first() or ClinicSetting()
    pdf_bytes = generate_invoice_pdf(inv, clinic)

    log_audit_event(
        db=db,
        action="INVOICE_PDF_DOWNLOADED",
        resource_type="invoice",
        actor=current_user,
        resource_id=inv.id,
        patient_id=inv.patient_id,
        request=request,
    )
    db.commit()

    filename = f"RumiDentalCare_{inv.invoice_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ============================================================================
# PAYMENTS ROUTER (/api/v1/payments)
# ============================================================================


@payments_router.get("")
def list_payments(
    patient_id: Optional[int] = Query(default=None),
    invoice_id: Optional[int] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = current_user.role.name if current_user.role else ""
    query = db.query(Payment)

    if role_name == ROLE_PATIENT:
        own = db.query(PatientProfile).filter(PatientProfile.user_id == current_user.id).first()
        if not own:
            return []
        if patient_id is not None and patient_id != own.id:
            verify_patient_isolation(db, current_user, patient_id, request, "payment")
        query = query.filter(Payment.patient_id == own.id)
    elif patient_id is not None:
        verify_patient_isolation(db, current_user, patient_id, request, "payment")
        query = query.filter(Payment.patient_id == patient_id)

    if invoice_id is not None:
        query = query.filter(Payment.invoice_id == invoice_id)

    items = query.order_by(Payment.payment_date.desc(), Payment.id.desc()).all()
    if date_from:
        items = [p for p in items if p.payment_date.date() >= date_from]
    if date_to:
        items = [p for p in items if p.payment_date.date() <= date_to]
    return [_serialize_payment(p) for p in items]


@payments_router.post("", status_code=status.HTTP_201_CREATED)
def record_payment(
    payload: PaymentRecordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """
    Records an actual verified payment against an Invoice and atomically issues an official Receipt.
    Supports partial and full payments with Decimal-safe arithmetic.
    """
    inv = db.query(Invoice).filter(Invoice.id == payload.invoice_id).first()
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    if inv.document_kind == "Estimate":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot record payment against a Cost Estimate. Convert or issue an Invoice first.",
        )
    if inv.status == "Voided":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot pay a voided invoice.")

    pay_amount = _d(payload.amount)
    if pay_amount <= Decimal("0.00"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment amount must be positive.")
    if pay_amount > _d(inv.balance_due):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment amount (PKR {pay_amount:,.2f}) exceeds remaining invoice balance (PKR {inv.balance_due:,.2f}).",
        )

    year = datetime.now(timezone.utc).year
    pay_seq = db.query(Payment).count() + 1
    pay_num = f"PAY-{year}-{pay_seq:05d}"
    while db.query(Payment).filter(Payment.payment_number == pay_num).first():
        pay_seq += 1
        pay_num = f"PAY-{year}-{pay_seq:05d}"

    payment = Payment(
        payment_number=pay_num,
        invoice_id=inv.id,
        patient_id=inv.patient_id,
        amount=pay_amount,
        currency="PKR",
        payment_method=payload.payment_method.strip(),
        reference_number=payload.reference_number,
        status="Recorded",
        received_by_user_id=current_user.id,
        notes=payload.notes,
    )
    db.add(payment)
    db.flush()

    rcp_seq = db.query(Receipt).count() + 1
    rcp_num = f"RCP-{year}-{rcp_seq:05d}"
    while db.query(Receipt).filter(Receipt.receipt_number == rcp_num).first():
        rcp_seq += 1
        rcp_num = f"RCP-{year}-{rcp_seq:05d}"

    receipt = Receipt(
        receipt_number=rcp_num,
        payment_id=payment.id,
        invoice_id=inv.id,
        patient_id=inv.patient_id,
        amount_received=pay_amount,
        currency="PKR",
        payment_method=payment.payment_method,
        issued_by_user_id=current_user.id,
        notes=payload.notes or f"Official payment receipt for {inv.invoice_number}",
    )
    db.add(receipt)
    db.flush()

    db.refresh(inv)
    _recalculate_invoice_totals(inv)

    if inv.patient and inv.patient.user_id:
        create_user_notification(
            db=db,
            user_id=inv.patient.user_id,
            title=f"Payment Recorded & Receipt {rcp_num} Issued",
            message=f"Payment of PKR {pay_amount:,.2f} received for {inv.invoice_number}. Remaining balance: PKR {inv.balance_due:,.2f}.",
            notification_type="Receipt",
            related_entity_type="receipt",
            related_entity_id=receipt.id,
        )

    log_audit_event(
        db=db,
        action="PAYMENT_RECORDED_AND_RECEIPT_ISSUED",
        resource_type="payment",
        actor=current_user,
        resource_id=payment.id,
        patient_id=inv.patient_id,
        request=request,
        details={
            "payment_number": pay_num,
            "receipt_number": rcp_num,
            "invoice_number": inv.invoice_number,
            "amount": str(pay_amount),
            "remaining_balance": str(inv.balance_due),
        },
    )
    db.commit()
    db.refresh(payment)
    return _serialize_payment(payment)


@payments_router.post("/{payment_id}/reverse")
def reverse_payment(
    payment_id: int,
    payload: PaymentReverseRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """
    Traceable financial reversal: preserves payment & receipt rows for accounting history,
    marks payment as Reversed, voids the associated receipt, and recalculates invoice balance.
    """
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found.")
    if payment.status == "Reversed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment is already reversed.")

    payment.status = "Reversed"
    payment.reversal_reason = payload.reversal_reason.strip()
    payment.reversed_at = datetime.now(timezone.utc)
    payment.reversed_by_user_id = current_user.id

    if payment.receipt:
        payment.receipt.is_voided = True

    inv = payment.invoice
    db.flush()
    db.refresh(inv)
    _recalculate_invoice_totals(inv)

    log_audit_event(
        db=db,
        action="PAYMENT_REVERSED",
        resource_type="payment",
        actor=current_user,
        resource_id=payment.id,
        patient_id=payment.patient_id,
        request=request,
        details={"payment_number": payment.payment_number, "reason": payment.reversal_reason},
    )
    db.commit()
    db.refresh(payment)
    return _serialize_payment(payment)


@payments_router.get("/export.csv")
def export_payments_csv(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    payments = db.query(Payment).order_by(Payment.payment_date.desc()).all()
    if date_from:
        payments = [p for p in payments if p.payment_date.date() >= date_from]
    if date_to:
        payments = [p for p in payments if p.payment_date.date() <= date_to]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Payment Number",
            "Receipt Number",
            "Invoice Number",
            "Patient Number",
            "Patient Name",
            "Amount (PKR)",
            "Method",
            "Status",
            "Payment Date",
        ]
    )
    for p in payments:
        writer.writerow(
            [
                p.payment_number,
                p.receipt.receipt_number if p.receipt else "",
                p.invoice.invoice_number if p.invoice else "",
                p.patient.patient_number if p.patient else "",
                p.patient.full_name if p.patient else "",
                f"{p.amount:.2f}",
                p.payment_method,
                p.status,
                p.payment_date.strftime("%Y-%m-%d %H:%M"),
            ]
        )

    log_audit_event(
        db=db,
        action="FINANCIAL_CSV_EXPORTED",
        resource_type="payment",
        actor=current_user,
        request=request,
        details={"rows": len(payments)},
    )
    db.commit()

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="RumiDentalCare_Payments_Report.csv"'},
    )


# ============================================================================
# RECEIPTS ROUTER (/api/v1/receipts)
# ============================================================================


@receipts_router.get("")
def list_receipts(
    patient_id: Optional[int] = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = current_user.role.name if current_user.role else ""
    query = db.query(Receipt)

    if role_name == ROLE_PATIENT:
        own = db.query(PatientProfile).filter(PatientProfile.user_id == current_user.id).first()
        if not own:
            return []
        if patient_id is not None and patient_id != own.id:
            verify_patient_isolation(db, current_user, patient_id, request, "receipt")
        query = query.filter(Receipt.patient_id == own.id)
    elif patient_id is not None:
        verify_patient_isolation(db, current_user, patient_id, request, "receipt")
        query = query.filter(Receipt.patient_id == patient_id)

    items = query.order_by(Receipt.issued_at.desc(), Receipt.id.desc()).all()
    return [_serialize_receipt(r) for r in items]


@receipts_router.get("/{receipt_id}")
def get_receipt(
    receipt_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rcp = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not rcp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found.")

    verify_patient_isolation(db, current_user, rcp.patient_id, request, "receipt")
    return _serialize_receipt(rcp)


@receipts_router.get("/{receipt_id}/pdf")
def download_receipt_pdf(
    receipt_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rcp = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not rcp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found.")

    verify_patient_isolation(db, current_user, rcp.patient_id, request, "receipt")
    clinic = db.query(ClinicSetting).first() or ClinicSetting()
    pdf_bytes = generate_receipt_pdf(rcp, rcp.payment, rcp.invoice, clinic)

    log_audit_event(
        db=db,
        action="RECEIPT_PDF_DOWNLOADED",
        resource_type="receipt",
        actor=current_user,
        resource_id=rcp.id,
        patient_id=rcp.patient_id,
        request=request,
    )
    db.commit()

    filename = f"RumiDentalCare_{rcp.receipt_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
