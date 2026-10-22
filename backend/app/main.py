"""Rumi Dental Care — FastAPI Application Entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
import app.models  # noqa: F401
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services.seed_service import seed_initial_data
from app.web_routes import web_router


_DB_INITIALIZED = False


def ensure_Runtime_db_ready() -> None:
    """Idempotently ensures tables and baseline clinic seed data exist (works on both Uvicorn & Vercel)."""
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return
    try:
        settings.private_upload_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass
    db = SessionLocal()
    try:
        seed_initial_data(db)
        _DB_INITIALIZED = True
    except Exception:
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure upload directories and database tables exist, and seed baseline clinic data if empty."""
    ensure_Runtime_db_ready()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "Full-Stack Dental Clinic Website & Management System for Rumi Dental Care "
        "(388 A, Block A, RECHS, Johar Town, Lahore)."
    ),
    lifespan=lifespan,
)

# Security & CORS Middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Static assets (PUBLIC ONLY — private clinical uploads are never mounted here)
STATIC_DIR = Path(__file__).resolve().parent / "static"
try:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def vercel_serverless_init_middleware(request: Request, call_next):
    if not _DB_INITIALIZED:
        ensure_Runtime_db_ready()
    return await call_next(request)

# Include REST API v1 and Web/HTML routes
app.include_router(api_router, prefix="/api/v1")
app.include_router(web_router)


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint for monitoring and readiness probes."""
    return {
        "status": "healthy",
        "clinic": settings.APP_NAME,
        "lead_dentist": "Dr. Aisha Salman",
        "version": "1.0.0",
    }


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """Return JSON for API requests and clean HTML/JSON as appropriate."""
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    accept = request.headers.get("accept", "")
    if "text/html" in accept and exc.status_code in (401, 403, 404):
        return HTMLResponse(
            status_code=exc.status_code,
            content=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{exc.status_code} | Rumi Dental Care</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-[#f6f9f9] text-[#07263b] min-h-screen flex items-center justify-center p-6">
  <div class="max-w-md w-full bg-white rounded-2xl shadow-lg border border-slate-200 p-8 text-center">
    <div class="w-14 h-14 rounded-full bg-[#01578c]/10 text-[#01578c] flex items-center justify-center mx-auto mb-4 font-bold text-xl">
      {exc.status_code}
    </div>
    <h1 class="text-xl font-bold mb-2">Access Restricted ({exc.status_code})</h1>
    <p class="text-sm text-slate-600 mb-6">{exc.detail}</p>
    <div class="flex flex-wrap justify-center gap-3">
      <a href="/" class="px-4 py-2 rounded-lg bg-[#01578c] text-white text-sm font-semibold">Return Home</a>
      <a href="/login" class="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 text-sm font-semibold">Patient Login</a>
      <a href="/staff/login" class="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 text-sm font-semibold">Staff Login</a>
    </div>
  </div>
</body>
</html>""",
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Consistent validation error format without stack traces."""
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(x) for x in err.get("loc", []))
        errors.append(f"{loc}: {err.get('msg', 'Invalid input')}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": "; ".join(errors) if errors else "Validation error",
            "errors": exc.errors(),
        },
    )
