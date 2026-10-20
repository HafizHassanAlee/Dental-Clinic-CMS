"""Root package shim allowing `uvicorn app.main:app` and `python -m app.cli` from repository root."""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Extend package __path__ so `app.*` submodules resolve directly to `backend/app/*`
__path__.append(str(_BACKEND_DIR / "app"))  # type: ignore[name-defined]
