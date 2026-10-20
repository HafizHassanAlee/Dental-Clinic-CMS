# Rumi Dental Care — Full-Stack Dental Clinic Website & Management System

Complete, responsive, production-grade dental clinic website and clinical management platform built for **Rumi Dental Care** ([https://rumidentalcare.com/](https://rumidentalcare.com/)).

---

## 1. Genuine Clinic Profile (Preserved from `rumidentalcare.com`)

- **Clinic Name**: Rumi Dental Care
- **Lead Dental Surgeon**: Dr. Aisha Salman
- **Address**: 388 A, Block A, RECHS, Johar Town, Lahore, Pakistan
- **Phone / WhatsApp**: `+92 310 2468080`
- **Opening Hours**: Monday – Saturday, `04:00 PM – 10:00 PM` (Sunday Closed)
- **Brand Palette**:
  - Primary Deep Dental Blue: `#01578c`
  - Accent Dental Teal: `#29d8db`
  - Soft Neutral Clinical Background: `#f6f9f9`
  - Deep Slate Heading Ink: `#07263b`
- **Currency**: `PKR` (Pakistani Rupee — server-side `Decimal` arithmetic)
- **Verified Public Testimonials**: Uswa Syed, Sherazi Surayya, Haris Muhammad

---

## 2. Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Backend Framework** | Python 3.12+ / FastAPI / Uvicorn |
| **Database & ORM** | PostgreSQL 16+ / SQLAlchemy 2.x (34 normalized tables) |
| **Migrations** | Alembic (`backend/alembic/versions/47ac646bd68d_initial_rumi_dental_schema.py`) |
| **Validation & Config** | Pydantic v2 & `pydantic-settings` |
| **Authentication & Security** | `bcrypt` password hashing, signed JWT + `HttpOnly` cookies, CSRF token verification, account lockout, `token_version` revocation, `verify_patient_isolation` |
| **PDF Engine** | `fpdf2` (Branded PDFs for Invoices, Official Payment Receipts, Prescriptions, and Treatment Summaries) |
| **Frontend** | Responsive Jinja2 + Tailwind CSS + Chart.js + Interactive FDI Odontogram (served directly by FastAPI) AND modular React + TypeScript + Vite SPA workspace in `frontend/` |
| **Automated Testing** | Pytest + FastAPI `TestClient` against isolated `rumi_dental_test` PostgreSQL database |

---

## 3. Repository Structure

```text
rumi_dental/
├── .env.example                     # Environment variable template (placeholders only)
├── .gitignore                       # Git ignore rules
├── alembic.ini                      # Root Alembic configuration
├── conftest.py                      # Root Pytest path configuration
├── requirements.txt                 # Python dependencies
├── README.md                        # Project documentation
├── app/                             # Root Python package shim -> backend/app
├── docs/
│   └── SECURITY_AND_DEPLOYMENT.md   # Security architecture & production deployment guide
├── scripts/
│   └── backup_restore.ps1           # PostgreSQL + private_uploads backup & restore script
├── frontend/                        # React + TypeScript + Vite SPA workspace
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── components/DentalChart.tsx
│       ├── services/api.ts
│       └── types/index.ts
└── backend/
    ├── alembic.ini
    ├── alembic/                     # Alembic migration environment & versions
    ├── private_uploads/             # Confidential X-ray & document storage (outside /static)
    ├── tests/
    │   └── test_rumi_dental.py      # End-to-end automated security, clinical & financial test suite
    └── app/
        ├── main.py                  # FastAPI application entrypoint
        ├── cli.py                   # Secure admin provisioning & seed CLI
        ├── web_routes.py            # Public website & role-protected portal HTML routes
        ├── core/                    # Config, bcrypt/JWT security, RBAC permissions
        ├── db/                      # SQLAlchemy 2.x declarative base & session management
        ├── dependencies/            # Auth & strict patient-level isolation dependencies
        ├── middleware/              # HTTP security headers middleware
        ├── models/                  # 34 normalized SQLAlchemy 2.x ORM models
        ├── schemas/                 # Pydantic v2 request/response schemas
        ├── services/                # FDI dental chart catalog, PDF generator, notifications, seed
        ├── api/v1/                  # Modular REST API routers (/api/v1/*)
        ├── static/                  # Public CSS, JS, and genuine clinic images
        └── templates/               # Public pages, separated login pages, and 3 role portals
```

---

## 4. Quick Start & Local Setup

### Step 1: Configure Environment Variables

Copy `.env.example` to `.env` and update your local PostgreSQL connection string and secrets if needed:

```powershell
Copy-Item .env.example .env
```

### Step 2: Install Python Dependencies

```powershell
pip install -r requirements.txt
```

### Step 3: Create PostgreSQL Databases & Run Alembic Migrations

Ensure PostgreSQL is running on `localhost:5432` with databases `rumi_dental` and `rumi_dental_test`, then apply migrations:

```powershell
alembic upgrade head
```

### Step 4: Seed Genuine Clinic Data & Demo Records

```powershell
python -m app.cli seed
```

### Step 5: Provision an Administrator Account via Secure CLI

No public administrator registration form exists. Create or update an administrator account via the CLI:

```powershell
python -m app.cli create-admin --email admin@rumidentalcare.com --name "Rumi Clinic Administrator" --phone "+92 310 2468080"
```

### Step 6: Start the Application Server

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open **`http://127.0.0.1:8000`** in your browser:
- **Public Website**: `http://127.0.0.1:8000/`
- **Public Patient Login**: `http://127.0.0.1:8000/login`
- **Dedicated Staff Login (Doctors & Admins)**: `http://127.0.0.1:8000/staff/login`
- **Patient Portal**: `http://127.0.0.1:8000/patient/dashboard`
- **Doctor Clinical Workspace**: `http://127.0.0.1:8000/doctor/dashboard`
- **Administrator Dashboard**: `http://127.0.0.1:8000/admin/dashboard`
- **Interactive OpenAPI Docs**: `http://127.0.0.1:8000/docs`

---

## 5. Seeded Development Test Accounts (Local Development Only)

When `python -m app.cli seed` is executed in local development, the following synthetic test accounts are provisioned:

| Role | Login Page | Email | Password | Redirect Target |
| :--- | :--- | :--- | :--- | :--- |
| **Administrator** | `/staff/login` | `admin@rumidentalcare.com` | `Admin@Rumi2026!` | `/admin/dashboard` |
| **Lead Doctor (Dr. Aisha Salman)** | `/staff/login` | `dr.aisha@rumidentalcare.com` | `Doctor@Rumi2026!` | `/doctor/dashboard` |
| **Demo Patient A** | `/login` | `amna.khan@example.com` | `Patient@Rumi2026!` | `/patient/dashboard` |
| **Demo Patient B** | `/login` | `usman.ali@example.com` | `Patient@Rumi2026!` | `/patient/dashboard` |

---

## 6. Role & Permission Matrix

| Capability | Visitor | Patient | Doctor | Administrator |
| :--- | :---: | :---: | :---: | :---: |
| Browse public pages, services & approved reviews | ✅ | ✅ | ✅ | ✅ |
| Self-register via `/register` | ✅ (Patient role only) | — | — | — |
| Sign in via `/login` (Patient Portal) | — | ✅ | ❌ (`403`) | ❌ (`403`) |
| Sign in via `/staff/login` (Staff Portal) | — | ❌ (`403`) | ✅ | ✅ |
| View/manage own appointments, dental chart, X-rays, prescriptions, invoices & receipts | — | ✅ (Own only) | — | — |
| Access another patient's medical or financial records | ❌ | ❌ (`403` + Audit Log) | ✅ (Clinical care) | ✅ (Authorized) |
| Create/amend clinical encounters, FDI tooth findings, treatment plans & prescriptions | ❌ | ❌ (`403`) | ✅ | ❌ |
| Upload confidential X-rays & clinical documents | ❌ | ❌ (`403`) | ✅ | ✅ |
| Create/manage doctor & staff accounts, services, clinic settings & audit logs | ❌ | ❌ (`403`) | ❌ (`403`) | ✅ |
| Record payments, issue official receipts & execute traceable payment reversals | ❌ | ❌ (`403`) | ❌ (`403`) | ✅ |

---

## 7. Running Automated Tests

Run the full Pytest suite against the isolated `rumi_dental_test` PostgreSQL database:

```powershell
python -m pytest -v
```

---

## 8. Database Backup & Restore

Use `scripts/backup_restore.ps1` to back up or restore both PostgreSQL (`rumi_dental`) and `backend/private_uploads/`:

```powershell
# Create timestamped SQL dump + private_uploads archive in ./backups/
.\scripts\backup_restore.ps1 -Action backup

# Restore from a backup SQL dump
.\scripts\backup_restore.ps1 -Action restore -BackupFile ".\backups\rumi_dental_YYYYMMDD_HHMMSS.sql"
```
