"""Pytest configuration for backend tests."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
