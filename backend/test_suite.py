"""
test_suite.py — Automated verification test suite for Veri-Byte backend.
"""

import io
import os
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
_backend_dir = str(Path(__file__).resolve().parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

import config
from server import app
from utils.image_utils import (
    cleanup_session_dir,
    create_session_temp_dir,
    read_image_cv2_safe,
    save_temp_upload,
    validate_image_file,
)
from utils.verhoeff import is_valid_aadhaar, validate_aadhaar, validate_pan, validate_vid


def create_dummy_image_bytes(width=200, height=200, color=(100, 150, 200)) -> bytes:
    """Helper to generate in-memory valid JPEG bytes."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_verhoeff_validators():
    print("[1/5] Testing Verhoeff & National ID Validators...")
    # Known valid test Aadhaar
    assert is_valid_aadhaar("234123412346") is True, "Expected valid Aadhaar checksum"
    assert is_valid_aadhaar("234123412340") is False, "Expected invalid Aadhaar checksum"

    valid, msg = validate_aadhaar("234123412346")
    assert valid is True, f"validate_aadhaar failed: {msg}"

    # Invalid Aadhaar: start with 0
    valid, msg = validate_aadhaar("012345678901")
    assert valid is False, "Aadhaar starting with 0 must be invalid"

    # PAN checks (4th character P = Individual)
    valid, msg = validate_pan("ABCPE1234F")
    assert valid is True and "Individual" in msg, f"PAN Individual check failed: {msg}"

    valid, msg = validate_pan("ABCZZ1234F")
    assert valid is False, "PAN with invalid entity code should fail"

    # VID check
    valid, msg = validate_vid("1234567890123456")
    assert valid is True, "16-digit VID should pass"
    print("  -> Verhoeff and ID validators PASSED.")


def test_session_isolation_and_cleanup():
    print("[2/5] Testing Session Directory Isolation & Safe Cleanup...")
    sess1 = create_session_temp_dir()
    sess2 = create_session_temp_dir()

    assert sess1.exists() and sess1.is_dir(), "Session 1 dir must exist"
    assert sess2.exists() and sess2.is_dir(), "Session 2 dir must exist"
    assert sess1 != sess2, "Session dirs must be distinct"

    dummy_bytes = create_dummy_image_bytes()
    file1 = save_temp_upload(dummy_bytes, "test1.jpg", session_dir=sess1)
    file2 = save_temp_upload(dummy_bytes, "test2.jpg", session_dir=sess2)

    assert Path(file1).exists(), "File 1 must exist"
    assert Path(file2).exists(), "File 2 must exist"

    # Cleanup session 1 ONLY
    cleanup_session_dir(sess1)

    assert not Path(file1).exists(), "File 1 must be deleted"
    assert not sess1.exists(), "Session 1 dir must be deleted"
    assert Path(file2).exists(), "File 2 must still exist! (No race condition)"
    assert sess2.exists(), "Session 2 dir must remain intact"

    # Cleanup session 2
    cleanup_session_dir(sess2)
    assert not sess2.exists()
    print("  -> Session isolation and cleanup PASSED.")


def test_safe_image_cv2():
    print("[3/5] Testing Safe OpenCV Image Reading across Windows Paths...")
    sess = create_session_temp_dir()
    dummy_bytes = create_dummy_image_bytes(300, 200, (255, 128, 64))
    file_path = save_temp_upload(dummy_bytes, "test image with spaces & symbols.jpg", session_dir=sess)

    cv_img = read_image_cv2_safe(file_path)
    assert cv_img is not None, "Failed to read image with spaces via read_image_cv2_safe"
    assert cv_img.shape == (200, 300, 3), f"Expected shape (200, 300, 3), got {cv_img.shape}"

    cleanup_session_dir(sess)
    print("  -> Safe OpenCV path reading PASSED.")


def test_upload_validation_guards():
    print("[4/5] Testing Upload Validation (MIME & Size Limits)...")
    sess = create_session_temp_dir()

    # 1. Non-image corrupted bytes
    corrupt_bytes = b"NOT_AN_IMAGE_FILE_DATA_HEX_CORRUPT"
    try:
        save_temp_upload(corrupt_bytes, "fake.jpg", session_dir=sess)
        assert False, "Should have raised ValueError on corrupt image bytes"
    except ValueError as e:
        assert "not a recognized image" in str(e).lower() or "corrupted" in str(e).lower()

    # 2. Oversized file
    try:
        save_temp_upload(dummy_bytes := create_dummy_image_bytes(), "big.jpg", session_dir=sess, max_bytes=10)
        assert False, "Should have raised ValueError on oversized upload"
    except ValueError as e:
        assert "exceeds maximum allowed limit" in str(e).lower()

    cleanup_session_dir(sess)
    print("  -> Upload validation guards PASSED.")


def test_api_endpoints():
    print("[5/5] Testing FastAPI Endpoints...")
    client = TestClient(app)

    # Health check
    res = client.get("/api/health")
    assert res.status_code == 200
    health_data = res.json()
    assert health_data["status"] == "healthy"
    assert "models" in health_data

    # Synchronous screening endpoint with valid dummy image
    img_bytes = create_dummy_image_bytes(600, 400, (240, 240, 240))
    files = {
        "id_file": ("test_id.jpg", io.BytesIO(img_bytes), "image/jpeg"),
    }
    sync_res = client.post("/api/analyze/sync", files=files)
    assert sync_res.status_code == 200, f"Sync analyze failed: {sync_res.text}"
    sync_data = sync_res.json()

    assert "verdict" in sync_data
    assert "report" in sync_data
    assert "reasons" in sync_data
    assert isinstance(sync_data["reasons"], list)
    assert len(sync_data["reasons"]) > 0, "Reasons array must not be empty"

    print(f"  -> Pipeline executed. Verdict: {sync_data['verdict']}, Reasons: {sync_data['reasons']}")
    print("  -> API endpoints PASSED.")


if __name__ == "__main__":
    print("=====================================================================")
    print("Running Veri-Byte Full-Stack Backend Verification Suite")
    print("=====================================================================")
    test_verhoeff_validators()
    test_session_isolation_and_cleanup()
    test_safe_image_cv2()
    test_upload_validation_guards()
    test_api_endpoints()
    print("=====================================================================")
    print("ALL TESTS PASSED WITH 100% SUCCESS!")
    print("=====================================================================")
