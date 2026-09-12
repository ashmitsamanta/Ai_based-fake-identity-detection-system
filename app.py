"""
app.py — Hugging Face Spaces Native Python Entry Point.

Runs the Veri-Byte FastAPI Forensic Document Screening API directly on port 7860
with 16 GB free RAM and zero Docker requirement.
"""

import os
import sys
from pathlib import Path

# Ensure backend directory is in Python path
_root = Path(__file__).resolve().parent
_backend = _root / "backend"
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import uvicorn
from backend.server import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
