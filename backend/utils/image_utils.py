"""
utils/image_utils.py — Robust File-handling and Computer Vision Utilities.

Provides session-isolated file storage, early validation against malformed or oversized
uploads, safe image reading across Windows paths with spaces/Unicode, and non-blocking
lifecycle cleanup to prevent cross-request race conditions.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

import config

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE_BYTES: int = 15 * 1024 * 1024  # 15 MB threshold


def create_session_temp_dir() -> Path:
    """Create and return an isolated temporary directory for a single analysis session."""
    session_id = uuid.uuid4().hex
    session_dir = config.TEMP_DIR / f"sess_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def cleanup_session_dir(session_dir: Path | str | None) -> None:
    """
    Safely delete a session directory and all its contents.
    Ensures that finishing one request never touches concurrent requests.
    """
    if not session_dir:
        return
    p = Path(session_dir)
    if not p.exists():
        return
    try:
        shutil.rmtree(p, ignore_errors=True)
        logger.debug("Cleaned up session directory: %s", p)
    except Exception as exc:
        logger.warning("Failed to clean up session directory %s: %s", p, exc)


def read_image_cv2_safe(image_path: str | Path) -> Optional[np.ndarray]:
    """
    Robustly read an image file into an OpenCV BGR numpy array.

    Unlike standard `cv2.imread()`, this function handles Windows paths with spaces,
    Unicode characters, and network/relative paths by reading raw bytes first and
    decoding in-memory.

    Returns:
        np.ndarray (BGR image) or None if read/decode failed.
    """
    p = Path(image_path)
    if not p.is_file():
        logger.warning("read_image_cv2_safe: File not found: %s", image_path)
        return None
    try:
        raw_bytes = np.fromfile(str(p), dtype=np.uint8)
        img = cv2.imdecode(raw_bytes, cv2.IMREAD_COLOR)
        if img is None:
            logger.warning("read_image_cv2_safe: Failed to decode image: %s", image_path)
        return img
    except Exception as exc:
        logger.warning("read_image_cv2_safe failed for %s: %s", image_path, exc)
        return None


def validate_image_file(path: str | Path) -> bool:
    """
    Check whether the file at *path* is a valid, openable image.
    Uses PIL's Image.verify() without decoding full pixel data.
    """
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except (UnidentifiedImageError, OSError):
        return False


def save_temp_upload(
    file_or_bytes: Any,
    filename: str | None = None,
    session_dir: Path | str | None = None,
    max_bytes: int = MAX_UPLOAD_SIZE_BYTES,
) -> str:
    """
    Persist an uploaded file (FastAPI UploadFile, file-like, or bytes) to disk
    inside an isolated session directory or config.TEMP_DIR.

    Performs file size and image integrity checks.
    """
    detected_name = (
        filename
        or getattr(file_or_bytes, "filename", None)
        or getattr(file_or_bytes, "name", None)
        or "upload.jpg"
    )
    suffix: str = Path(detected_name).suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"):
        suffix = ".jpg"

    target_dir = Path(session_dir) if session_dir else config.TEMP_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    temp_path: Path = target_dir / f"{uuid.uuid4().hex}{suffix}"

    if isinstance(file_or_bytes, (bytes, bytearray)):
        content = bytes(file_or_bytes)
    elif hasattr(file_or_bytes, "file") and hasattr(file_or_bytes.file, "read"):
        content = file_or_bytes.file.read()
    elif hasattr(file_or_bytes, "read"):
        content = file_or_bytes.read()
    elif hasattr(file_or_bytes, "getbuffer"):
        content = bytes(file_or_bytes.getbuffer())
    else:
        raise ValueError("Unsupported upload file type")

    if len(content) > max_bytes:
        raise ValueError(
            f"File size exceeds maximum allowed limit of {max_bytes // (1024 * 1024)} MB."
        )

    # Basic header verification using PIL to prevent uploading non-image data
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
    except Exception as exc:
        raise ValueError(f"Uploaded file is corrupted or not a recognized image: {exc}")

    with open(temp_path, "wb") as f:
        f.write(content)

    return str(temp_path)


def cleanup_stale_temp_dirs(max_age_seconds: int = 3600) -> int:
    """
    Clean up orphaned session directories or files older than max_age_seconds.
    Safe to run periodically or on startup.
    """
    now = time.time()
    cleaned = 0
    if not config.TEMP_DIR.exists():
        return 0

    for item in config.TEMP_DIR.iterdir():
        try:
            mtime = item.stat().st_mtime
            if (now - mtime) > max_age_seconds:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
                cleaned += 1
        except OSError:
            pass
    return cleaned


def cleanup_all_temp() -> None:
    """
    Backward-compatible fallback: Clean up files in TEMP_DIR.
    Leaves subdirectories untouched if they were created recently (< 5 minutes)
    to protect concurrent sessions.
    """
    cleaned_stale = cleanup_stale_temp_dirs(max_age_seconds=300)
    logger.debug("Cleaned %d stale temp item(s)", cleaned_stale)

