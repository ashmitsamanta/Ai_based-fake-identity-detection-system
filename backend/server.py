"""
server.py — FastAPI Backend API for Veri-Byte Forensic Document Inspector.

Exposes the forensic analysis pipeline (agent.forensic_agent.run_analysis)
via Server-Sent Events (SSE) and JSON endpoints. Keeps all backend logic
strictly identical to the original pipeline.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
from pathlib import Path
from typing import Optional

# Ensure backend directory is in sys.path
_backend_dir = str(Path(__file__).resolve().parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import config
from agent.forensic_agent import run_analysis
from utils.image_utils import cleanup_all_temp, save_temp_upload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("veri-byte-api")

app = FastAPI(
    title="Veri-Byte Forensic Inspector API",
    version="2.0.0",
    description="High-performance biometric and forensic document screening API",
)

# Enable CORS for local React development (Vite runs on 5173 by default)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    """Return health status and current forensic configuration thresholds."""
    return {
        "status": "healthy",
        "service": "Veri-Byte Document Inspector",
        "models": {
            "biometric": "InsightFace buffalo_l",
            "deepfake": config.DEEPFAKE_MODEL_NAME,
            "ocr": "Tesseract OCR",
        },
        "thresholds": {
            "biometric_reject": config.BIOMETRIC_REJECT_THRESHOLD,
            "biometric_review": config.BIOMETRIC_REVIEW_THRESHOLD,
            "deepfake_reject": config.DEEPFAKE_REJECT_THRESHOLD,
            "deepfake_review": config.DEEPFAKE_REVIEW_THRESHOLD,
            "ocr_confidence": config.OCR_CONFIDENCE_THRESHOLD,
        },
    }


def _save_data_url(data_url: str, filename_prefix: str = "selfie") -> str:
    """Decode a base64 Data URL (from webcam capture) and persist to temp folder."""
    try:
        header, encoded = data_url.split(",", 1)
        suffix = ".jpg"
        if "image/png" in header:
            suffix = ".png"
        elif "image/webp" in header:
            suffix = ".webp"

        image_bytes = base64.b64decode(encoded)
        return save_temp_upload(image_bytes, f"{filename_prefix}{suffix}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid selfie data URL: {exc}")


def _encode_image_to_base64(image_path: str) -> Optional[str]:
    """Read an image file and return its data URL base64 string."""
    try:
        p = Path(image_path)
        if p.exists():
            with open(p, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
                return f"data:image/jpeg;base64,{encoded}"
    except Exception as exc:
        logger.warning("Failed to encode image %s to base64: %s", image_path, exc)
    return None


@app.post("/api/analyze")
async def analyze_document_stream(
    id_file: UploadFile = File(...),
    selfie_file: Optional[UploadFile] = File(None),
    selfie_data: Optional[str] = Form(None),
):
    """
    Stream forensic analysis progress step-by-step using Server-Sent Events (SSE).

    Pipeline stages:
    1. Biometric Gatekeeper (InsightFace face match)
    2. Deepfake / AI-Generation Check (SigLIP + multi-signal CV)
    3. OCR / MRZ Extraction (Tesseract / passporteye)
    4. Tampering Detection (Error Level Analysis + EXIF inspection)
    5. Verdict & Forensic Report Generation

    Accepts:
    - id_file: The uploaded ID document image (passport, national ID, PAN, etc.)
    - selfie_file: Live selfie image file OR
    - selfie_data: Base64 data URL captured directly from browser webcam.
    """
    try:
        # Save ID card to temp upload dir
        id_path = save_temp_upload(id_file)

        # Save Selfie (file or webcam data URL)
        if selfie_file is not None and selfie_file.filename:
            selfie_path = save_temp_upload(selfie_file)
        elif selfie_data:
            selfie_path = _save_data_url(selfie_data, "selfie_capture")
        else:
            raise HTTPException(status_code=400, detail="Live selfie is required for verification.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to process upload files: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to process uploads: {exc}")

    def event_generator():
        try:
            for update in run_analysis(id_path, selfie_path):
                # When verdict completes, embed base64 ELA visualization before cleanup
                if update.get("step") == "verdict" and update.get("status") == "complete":
                    results = update.get("results", {})
                    tamper_res = results.get("tampering", {})
                    ela_path = tamper_res.get("ela_image_path")
                    if ela_path:
                        ela_b64 = _encode_image_to_base64(ela_path)
                        if ela_b64:
                            update["ela_image_base64"] = ela_b64

                # Send SSE formatted event
                data = json.dumps(update)
                yield f"data: {data}\n\n"

        except Exception as exc:
            logger.error("Pipeline streaming exception: %s", exc, exc_info=True)
            err_update = {
                "step": "verdict",
                "status": "error",
                "message": f"Pipeline internal error: {exc}",
                "verdict": "REJECT",
                "report": f"# Analysis Pipeline Error\n\nAn unexpected error occurred during analysis: `{exc}`",
                "results": {},
            }
            yield f"data: {json.dumps(err_update)}\n\n"
        finally:
            # Sensitive identity documents and selfies are cleaned up immediately
            cleanup_all_temp()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/analyze/sync")
async def analyze_document_sync(
    id_file: UploadFile = File(...),
    selfie_file: Optional[UploadFile] = File(None),
    selfie_data: Optional[str] = Form(None),
):
    """
    Synchronous fallback endpoint returning the complete forensic analysis
    result in a single JSON payload.
    """
    try:
        id_path = save_temp_upload(id_file)
        if selfie_file is not None and selfie_file.filename:
            selfie_path = save_temp_upload(selfie_file)
        elif selfie_data:
            selfie_path = _save_data_url(selfie_data, "selfie_capture")
        else:
            raise HTTPException(status_code=400, detail="Live selfie is required for verification.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to process uploads: {exc}")

    step_history = []
    final_payload = {}
    try:
        for update in run_analysis(id_path, selfie_path):
            step_history.append({
                "step": update.get("step"),
                "status": update.get("status"),
                "message": update.get("message"),
            })
            if update.get("step") == "verdict" and update.get("status") == "complete":
                final_payload = update

        # Convert ELA image to base64
        ela_path = final_payload.get("results", {}).get("tampering", {}).get("ela_image_path")
        ela_b64 = _encode_image_to_base64(ela_path) if ela_path else None

        return {
            "verdict": final_payload.get("verdict", "UNKNOWN"),
            "report": final_payload.get("report", ""),
            "results": final_payload.get("results", {}),
            "ela_image_base64": ela_b64,
            "steps": step_history,
        }
    finally:
        cleanup_all_temp()


# Mount React Production Build if present
dist_path = getattr(config, "FRONTEND_DIST_DIR", config.BASE_DIR.parent / "frontend" / "dist")
if dist_path.exists():
    app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="static")


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    uvicorn.run("server:app", host=host, port=port, reload=False)
