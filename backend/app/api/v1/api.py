from fastapi import APIRouter
from app.api.v1.endpoints import (
    admin_reports,
    appointments,
    auth,
    billing,
    clinical_records,
    dental_chart,
    doctors,
    documents,
    notifications,
    patients,
    prescriptions,
    reviews,
    services,
    treatments,
)


api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(patients.router, prefix="/patients", tags=["Patients"])
api_router.include_router(doctors.router, prefix="/doctors", tags=["Doctors"])
api_router.include_router(appointments.router, prefix="/appointments", tags=["Appointments"])
api_router.include_router(services.router, prefix="/services", tags=["Services"])
api_router.include_router(clinical_records.router, prefix="/clinical-records", tags=["Clinical Records"])
api_router.include_router(dental_chart.router, prefix="/dental-chart", tags=["Dental Chart (FDI)"])
api_router.include_router(treatments.router, prefix="/treatments", tags=["Treatments & Plans"])
api_router.include_router(prescriptions.router, prefix="/prescriptions", tags=["Prescriptions"])
api_router.include_router(documents.router, prefix="/documents", tags=["Clinical Documents & X-Rays"])
api_router.include_router(billing.invoices_router, prefix="/invoices", tags=["Invoices & Estimates"])
api_router.include_router(billing.payments_router, prefix="/payments", tags=["Payments"])
api_router.include_router(billing.receipts_router, prefix="/receipts", tags=["Receipts"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["Reviews & Testimonials"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(admin_reports.admin_router, prefix="/admin", tags=["Administration"])
api_router.include_router(admin_reports.reports_router, prefix="/reports", tags=["Reports & Analytics"])
