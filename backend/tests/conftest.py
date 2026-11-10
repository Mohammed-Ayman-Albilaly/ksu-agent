"""Pytest configuration for backend tests."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"

# backend/scripts holds the pipeline modules (retrieve, answer); backend/ holds the
# FastAPI package (app), so both go on the path for the tests.
for directory in (SCRIPTS_DIR, BACKEND_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
