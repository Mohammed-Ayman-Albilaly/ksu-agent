"""FastAPI app package for KSU Agent.

The RAG pipeline lives in backend/scripts (retrieve.py, answer.py) so the same
code serves the API, the CLI and the eval. This package adds that directory to
sys.path, the way eval/run_retrieval_eval.py already does.
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
