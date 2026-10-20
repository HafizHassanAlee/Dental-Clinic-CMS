# Security Architecture & Production Deployment Guide — Rumi Dental Care

## 1. Security Architecture Overview

Rumi Dental Care handles confidential patient dental records, X-rays, prescriptions, and billing data. The system enforces defense-in-depth across six layers:

1. **Separated Authentication Entry Points**:
   - **Public Patient Login (`/login`, `POST /api/v1/auth/patient/login`)**: Exclusively authenticates `patient` accounts. Doctor and Administrator accounts are explicitly rejected with `403 Forbidden`.
   - **Staff Login (`/staff/login`, `POST /api/v1/auth/staff/login`)**: Exclusively authenticates `doctor` and `admin` accounts. Patient accounts are rejected with `403 Forbidden`.
   - **No Public Admin Registration**: Public registration (`POST /api/v1/auth/register`) is hardwired on the server to assign the `patient` role (`ROLE_PATIENT`). Initial administrators are provisioned via the secure CLI (`python -m app.cli create-admin`), and doctor accounts are created strictly by authenticated administrators.

2. **Password Security & Account Lockout**:
   - Passwords are hashed using **bcrypt** (`$2b$12$...`) via `app/core/security.py`.
   - Password strength rules enforce minimum length, uppercase, lowercase, numeric, and special characters.
   - Repeated failed login attempts increment `failed_login_attempts` and trigger temporary account lockout (`locked_until`) after `LOGIN_MAX_ATTEMPTS` (default: 5 attempts for 15 minutes).
   - Password reset tokens are cryptographically random (`secrets.token_urlsafe(32)`), stored only as SHA-256 hashes in `password_reset_tokens`, expire after 30 minutes, and are single-use (`used_at`).

3. **Token Versioning & Immediate Session Revocation**:
   - Every `User` record includes a `token_version` counter embedded in signed JWTs.
   - When a user changes their password, resets their password, or is deactivated by an administrator (`PATCH /api/v1/admin/users/{id}/status?is_active=false`), `token_version` is incremented immediately, invalidating any previously issued tokens on the next request.

4. **Strict Patient-Level Data Isolation (`verify_patient_isolation`)**:
   - Centralized in `backend/app/dependencies/auth.py`.
   - Every endpoint serving patient profiles, appointments, clinical encounters, diagnoses, FDI dental charts, treatment plans, treatment records, prescriptions, clinical documents/X-rays, invoices, payments, and receipts verifies that:
     - If the caller is a `patient`, `target_patient_id == own_patient_profile.id`.
     - If a patient attempts to access another patient's record (`Patient A` → `Patient B`), the server logs an `UNAUTHORIZED_PATIENT_ACCESS_ATTEMPT` event in `audit_logs` and raises `403 Forbidden`.
     - Non-clinical administrative staff without `can_view_clinical_details` are prevented from viewing detailed clinical notes.

5. **Private Clinical Document & X-Ray Storage**:
   - Uploaded X-rays and clinical documents are stored in `backend/private_uploads/` **outside** `/static`.
   - Uploads are validated against an allowlist of extensions (`.jpg`, `.jpeg`, `.png`, `.pdf`, `.dcm`), MIME types, maximum file size (`MAX_UPLOAD_SIZE_MB`), and **magic file signature bytes** (`\x89PNG`, `\xff\xd8\xff`, `%PDF-`, `DICM`).
   - Files are renamed to UUIDs (`{uuid4}.{ext}`) to prevent path traversal and filename collisions, hashed with SHA-256 for integrity verification, and streamed only through `/api/v1/documents/{id}/download` after passing `verify_patient_isolation`.

6. **Immutable Clinical Amendments & Financial Traceability**:
   - Finalized clinical encounters (`status = "Finalized"`) cannot be silently overwritten. Post-finalization edits require an `amendment_reason`, increment `version`, set `status = "Amended"`, and persist a full JSON snapshot of the prior state in `encounter_amendments`.
   - Financial calculations use Python `Decimal` (`NUMERIC(12, 2)`) in `PKR`. Receipts are generated **exclusively** when an actual payment is recorded (`POST /api/v1/payments`). Payment reversals (`POST /api/v1/payments/{id}/reverse`) preserve accounting history, void the associated receipt, and recalculate `balance_due`.

---

## 2. Production Deployment Checklist

1. **Environment Configuration (`.env`)**:
   - Set `APP_ENV=production` and `DEBUG=false`.
   - Generate a strong 64-byte `SECRET_KEY`:
     ```bash
     python -c "import secrets; print(secrets.token_urlsafe(64))"
     ```
   - Set `COOKIE_SECURE=true` so `HttpOnly` authentication cookies are transmitted exclusively over HTTPS.
   - Configure `CORS_ORIGINS=https://rumidentalcare.com` to restrict cross-origin requests to the production domain.

2. **Database & Migrations**:
   - Run PostgreSQL 16+ with SSL enabled and a least-privilege application database role.
   - Apply schema migrations before starting application workers:
     ```bash
     alembic upgrade head
     ```
   - Provision the production administrator account securely (prompts for password without echoing):
     ```bash
     python -m app.cli create-admin --email admin@rumidentalcare.com --name "Clinic Administrator" --phone "+92 310 2468080"
     ```

3. **Reverse Proxy & TLS (Nginx / Caddy)**:
   - Terminate TLS 1.2/1.3 at Nginx or Caddy in front of Uvicorn/Gunicorn workers:
     ```bash
     uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4 --proxy-headers
     ```
   - Ensure `backend/private_uploads/` is never served by Nginx directly; all downloads must pass through FastAPI's `/api/v1/documents/{id}/download` authorization check.

4. **Automated Backups**:
   - Schedule `scripts/backup_restore.ps1 -Action backup` daily via Windows Task Scheduler or cron to back up both PostgreSQL (`pg_dump`) and `private_uploads/` to encrypted off-site storage.
