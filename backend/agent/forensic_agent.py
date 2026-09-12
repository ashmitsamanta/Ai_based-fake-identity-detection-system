"""
agent/forensic_agent.py — Document Screening Pipeline (Gatekeeper Version).

Pipeline stages:
1. **Gatekeeper Face Match** — biometrics run FIRST. If <90%, pipeline halts.
2. **OCR / MRZ extraction** — text recognition + document-type detection.
3. **Tampering detection** — Error Level Analysis + EXIF metadata check.
4. **Verdict** — deterministic decision matrix → APPROVED / REJECT / MANUAL REVIEW.

``run_analysis()`` is a **generator** so callers (such as the FastAPI SSE
streaming endpoint) can emit live, step-by-step progress. Each yielded dict
conforms to :class:`agent.types.StepUpdate`.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Generator, List, Optional, Tuple

import numpy as np
import pytesseract
from PIL import Image, ImageChops

import config
from agent.types import (
    BiometricResult,
    OcrResult,
    StepUpdate,
    TamperResult,
    Verdict,
)

# Import the new InsightFace engine
from agent.face_engine import compare_faces

# Import the deepfake / AI-generation detector
from agent.deepfake_detector import detect_deepfake

logger = logging.getLogger(__name__)
pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD

try:
    from passporteye import read_mrz
    HAS_PASSPORTEYE: bool = True
except ImportError:
    HAS_PASSPORTEYE = False
    logger.info("passporteye not installed — MRZ extraction unavailable")


# ── Public API ──────────────────────────────────────────────────

def run_analysis(
    id_path: str,
    selfie_path: Optional[str] = None,
) -> Generator[StepUpdate, None, None]:
    """
    Run the full forensic analysis pipeline on an identity document + selfie.

    This is a **generator** — it yields a :class:`~agent.types.StepUpdate` dict
    after each pipeline stage so callers (e.g. the FastAPI SSE endpoint) can stream
    live progress without waiting for the full pipeline to finish.

    Pipeline order
    --------------
    1. Biometric Gatekeeper  — if score < BIOMETRIC_REJECT_THRESHOLD → halt.
    2. Deepfake / AI check   — if confidence >= DEEPFAKE_REJECT_THRESHOLD → halt.
    3. OCR / MRZ extraction  — parse document text and detect document type.
    4. Tampering detection   — ELA heatmap + EXIF metadata inspection.
    5. Verdict               — deterministic decision matrix → APPROVED / REJECT / MANUAL REVIEW.

    Args:
        id_path:     Absolute filesystem path to the uploaded identity document image.
        selfie_path: Absolute filesystem path to the live selfie image. Required;
                     pipeline halts with REJECT if not provided.

    Yields:
        :class:`~agent.types.StepUpdate` dicts, one per stage transition.
        The final yield (step="verdict", status="complete") additionally includes
        ``verdict``, ``report``, and ``results`` keys.
    """

    results: dict = {}

    # ── Step 1: Gatekeeper Biometric Verification ─────────────
    yield {"step": "biometric", "status": "running", "message": "Running 90% Gatekeeper Face Match..."}

    if not selfie_path:
        yield {"step": "biometric", "status": "error", "message": "Missing selfie"}
        verdict = "REJECT"
        reasons = ["Gatekeeper blocked: Live selfie is mandatory for verification."]
        yield {
            "step": "verdict", "status": "complete", "message": "Rejected by Gatekeeper",
            "verdict": verdict, "report": _build_report(results, verdict, reasons), "results": results
        }
        return

    bio_result = _verify_face(id_path, selfie_path)
    results["biometric"] = bio_result

    if bio_result.get("error"):
        yield {"step": "biometric", "status": "error", "message": bio_result["error"]}
        verdict = "REJECT"
        reasons = [f"Gatekeeper failed: {bio_result['error']}"]
        yield {
            "step": "verdict", "status": "complete", "message": "Rejected by Gatekeeper",
            "verdict": verdict, "report": _build_report(results, verdict, reasons), "results": results
        }
        return

    score = bio_result.get("match_confidence", 0.0)
    if score < config.BIOMETRIC_REJECT_THRESHOLD:
        yield {"step": "biometric", "status": "error", "message": f"Match Failed: {score:.1f}%"}
        verdict = "REJECT"
        reasons = [f"Gatekeeper blocked: Biometric match ({score:.1f}%) is below the {config.BIOMETRIC_REJECT_THRESHOLD}% threshold."]
        yield {
            "step": "verdict", "status": "complete", "message": "Rejected by Gatekeeper",
            "verdict": verdict, "report": _build_report(results, verdict, reasons), "results": results
        }
        return

    yield {"step": "biometric", "status": "complete", "message": f"Gatekeeper Passed: {score:.1f}%"}


    # ── Step 2: Deepfake / AI-Generated Image Detection ────────────
    yield {"step": "deepfake", "status": "running", "message": f"Analysing document photo with {config.DEEPFAKE_MODEL_NAME}..."}
    deepfake_result = detect_deepfake(id_path)
    results["deepfake"] = deepfake_result

    if deepfake_result.get("error"):
        yield {
            "step": "deepfake", "status": "error",
            "message": f"Detection error (skipped): {deepfake_result['error']}",
        }
    else:
        df_confidence = deepfake_result.get("confidence", 0.0)
        df_is_ai = deepfake_result.get("is_ai_generated", False)

        if df_is_ai or df_confidence > config.DEEPFAKE_REJECT_THRESHOLD:
            yield {
                "step": "deepfake", "status": "error",
                "message": f"AI-Generated Image Detected (AI possibility: {df_confidence:.1f}% > {config.DEEPFAKE_REJECT_THRESHOLD:.0f}%) - REJECTED",
            }
            verdict = "REJECT"
            reasons = [
                f"Flagged AI Generated: AI possibility ({df_confidence:.1f}%) > {config.DEEPFAKE_REJECT_THRESHOLD:.0f}% threshold - rejected."
            ]
            yield {
                "step": "verdict", "status": "complete", "message": "Rejected: Flagged AI Generated",
                "verdict": verdict, "report": _build_report(results, verdict, reasons), "results": results,
            }
            return
        elif df_confidence > config.DEEPFAKE_REVIEW_THRESHOLD:
            yield {
                "step": "deepfake", "status": "error",
                "message": f"Flagged Suspicious: AI possibility ({df_confidence:.1f}% > {config.DEEPFAKE_REVIEW_THRESHOLD:.0f}%) - flagged for manual review",
            }
        else:
            yield {
                "step": "deepfake", "status": "complete",
                "message": f"Real Photo ({config.DEEPFAKE_REVIEW_THRESHOLD:.0f}%)",
            }



    # ── Step 3: OCR / MRZ Extraction ──────────────────────────
    yield {"step": "ocr", "status": "running", "message": "Extracting text from document..."}
    ocr_result = _extract_document_data(id_path)
    results["ocr"] = ocr_result

    if ocr_result["confidence"] < config.OCR_CONFIDENCE_THRESHOLD:
        yield {
            "step": "ocr", "status": "error",
            "message": f"Low-confidence extraction ({ocr_result['confidence']:.0f}%) — image may be too low quality"
        }
    else:
        yield {
            "step": "ocr", "status": "complete",
            "message": f"Detected {ocr_result['id_type']} — extraction confidence {ocr_result['confidence']:.0f}%"
        }


    # ── Step 4: Tampering Detection ───────────────────────────
    yield {"step": "tampering", "status": "running", "message": "Running Error Level Analysis + metadata check..."}
    tamper_result = _detect_tampering(id_path, ocr_result["id_type"])
    results["tampering"] = tamper_result

    tamper_msg = f"Integrity: {tamper_result['integrity_status']}"
    if tamper_result["flagged_zones"]:
        tamper_msg += f" — flagged: {', '.join(tamper_result['flagged_zones'])}"
    yield {
        "step": "tampering",
        "status": "complete" if tamper_result["integrity_status"] == "CLEAN" else "error",
        "message": tamper_msg,
    }


    # ── Step 5: Verdict ───────────────────────────────────────
    yield {"step": "verdict", "status": "running", "message": "Applying decision matrix..."}
    verdict, reasons = _apply_decision_matrix(results)
    report = _build_report(results, verdict, reasons)
    yield {
        "step": "verdict", "status": "complete", "message": f"Final verdict: {verdict}",
        "verdict": verdict, "report": report, "results": results,
    }


# ── Step Implementations ────────────────────────────────────────

def _verify_face(id_path: str, selfie_path: str) -> BiometricResult:
    """Compare using the InsightFace engine with raw image bytes."""
    try:
        with open(id_path, "rb") as f1, open(selfie_path, "rb") as f2:
            ref_bytes = f1.read()
            live_bytes = f2.read()

        result = compare_faces(ref_bytes, live_bytes)
        return {
            "match_confidence": result["similarity_score"],
            "raw_verified": result["similarity_score"] >= config.BIOMETRIC_REJECT_THRESHOLD,
        }
    except Exception as exc:
        logger.error("Face verification failed", exc_info=True)
        return {"error": f"Face verification failed: {exc}", "match_confidence": 0}


def _extract_document_data(id_path: str) -> OcrResult:
    img = Image.open(id_path)

    raw_text: str = pytesseract.image_to_string(img, config=config.TESSERACT_CONFIG)
    data = pytesseract.image_to_data(
        img, config=config.TESSERACT_CONFIG, output_type=pytesseract.Output.DICT,
    )
    confidences = [int(c) for c in data["conf"] if str(c) not in ("-1", "")]
    ocr_confidence: float = sum(confidences) / len(confidences) if confidences else 0.0

    if HAS_PASSPORTEYE:
        try:
            mrz = read_mrz(str(id_path))
            if mrz is not None:
                mrz_data = mrz.to_dict()
                checksum_valid = bool(mrz_data.get("valid_score", 0) >= 80)
                return {
                    "id_type": "Passport",
                    "confidence": ocr_confidence,
                    "raw_text": raw_text.strip(),
                    "fields": {
                        "name": f"{mrz_data.get('surname', '')} {mrz_data.get('names', '')}".strip(),
                        "passport_number": mrz_data.get("number", ""),
                        "nationality": mrz_data.get("nationality", ""),
                        "date_of_birth": mrz_data.get("date_of_birth", ""),
                        "date_of_expiry": mrz_data.get("expiration_date", ""),
                        "gender": mrz_data.get("sex", ""),
                    },
                    "format_valid": checksum_valid,
                }
        except Exception:
            logger.debug("MRZ extraction failed — falling back to domestic ID regex", exc_info=True)

    detected_type: Optional[str] = None
    matched_value: Optional[str] = None
    for doc_type, spec in config.REGEX_PATTERNS.items():
        match = re.search(spec["pattern"], raw_text)
        if match:
            detected_type = doc_type
            matched_value = spec["clean"](match.group())
            break

    dob_match: Optional[str] = None
    for pattern in config.DOB_PATTERNS:
        m = re.search(pattern, raw_text)
        if m:
            dob_match = m.group()
            break

    return {
        "id_type": detected_type or "National ID (unrecognized format)",
        "confidence": ocr_confidence,
        "raw_text": raw_text.strip(),
        "fields": {"id_number": matched_value, "date_of_birth": dob_match},
        "format_valid": matched_value is not None,
    }


def _detect_tampering(id_path: str, id_type: str) -> TamperResult:
    zones = config.PASSPORT_ZONES if id_type == "Passport" else config.ID_DOCUMENT_ZONES
    critical = config.CRITICAL_FIELDS_PASSPORT if id_type == "Passport" else config.CRITICAL_FIELDS_ID

    original = Image.open(id_path).convert("RGB")
    ela_path = str(config.TEMP_DIR / f"ela_{Path(id_path).stem}.jpg")
    original.save(ela_path, "JPEG", quality=config.ELA_QUALITY)
    resaved = Image.open(ela_path)
    diff = ImageChops.difference(original, resaved)

    diff_np = np.array(diff).astype(int)
    ela_visual = Image.fromarray(
        np.clip(diff_np * config.ELA_SCALE_FACTOR, 0, 255).astype("uint8"),
    )
    ela_visual.save(ela_path)

    gray_diff = np.array(diff.convert("L"))
    h, w = gray_diff.shape

    flagged_zones: List[str] = []
    for zone_name, (y0, y1, x0, x1) in zones.items():
        region = gray_diff[int(y0 * h) : int(y1 * h), int(x0 * w) : int(x1 * w)]
        if region.size and np.sum(region > config.ELA_SENSITIVITY) > config.ELA_MIN_REGION_AREA:
            flagged_zones.append(zone_name)

    suspicious_software: Optional[str] = None
    try:
        exif = original.getexif()
        software_tag = exif.get(305)
        if software_tag:
            for sw in config.SUSPICIOUS_SOFTWARE:
                if sw in str(software_tag).lower():
                    suspicious_software = software_tag
                    break
    except Exception:
        logger.debug("Failed to read EXIF data", exc_info=True)

    critical_flagged = [z for z in flagged_zones if z in critical]

    if suspicious_software or critical_flagged:
        integrity_status = "TAMPERED"
    elif flagged_zones:
        integrity_status = "SUSPICIOUS"
    else:
        integrity_status = "CLEAN"

    return {
        "integrity_status": integrity_status,
        "flagged_zones": flagged_zones,
        "critical_flagged": critical_flagged,
        "suspicious_software": suspicious_software,
        "ela_image_path": ela_path,
    }


def _apply_decision_matrix(results: dict) -> Tuple[Verdict, List[str]]:
    reasons: List[str] = []
    ocr: dict = results.get("ocr", {})
    tamper: dict = results.get("tampering", {})
    bio: dict = results.get("biometric", {})
    deepfake: dict = results.get("deepfake", {})

    # Deepfake check (reject if >80%, manual review if >66%)
    df_confidence: float = deepfake.get("confidence", 0.0)
    review_df = False

    if df_confidence > config.DEEPFAKE_REJECT_THRESHOLD:
        reasons.append(f"AI possibility ({df_confidence:.1f}%) > {config.DEEPFAKE_REJECT_THRESHOLD:.0f}% - flagged AI Generated and rejected")
        return "REJECT", reasons
    elif df_confidence > config.DEEPFAKE_REVIEW_THRESHOLD:
        reasons.append(f"Flagged Suspicious: AI possibility ({df_confidence:.1f}%) > {config.DEEPFAKE_REVIEW_THRESHOLD:.0f}% - requires manual review")
        review_df = True

    format_invalid = not ocr.get("format_valid", False)
    if format_invalid:
        reasons.append("Document text/MRZ failed format or checksum validation")

    critical_tamper = bool(tamper.get("critical_flagged"))
    if critical_tamper:
        reasons.append(f"Tampering detected in critical field(s): {', '.join(tamper['critical_flagged'])}")
    if tamper.get("suspicious_software"):
        reasons.append(f"Image metadata shows editing software: {tamper['suspicious_software']}")
        critical_tamper = True

    bio_score: float = bio.get("match_confidence", 0.0)

    if format_invalid or critical_tamper:
        return "REJECT", reasons

    low_ocr_conf = ocr.get("confidence", 0) < config.OCR_CONFIDENCE_THRESHOLD
    review_bio = config.BIOMETRIC_REJECT_THRESHOLD <= bio_score < config.BIOMETRIC_REVIEW_THRESHOLD

    if low_ocr_conf:
        reasons.append("OCR/MRZ confidence too low to be certain")
    if review_bio:
        reasons.append(f"Biometric match in review range: {bio_score:.1f}%")

    if low_ocr_conf or review_bio or review_df:
        return "MANUAL REVIEW", reasons

    reasons.append("All checks passed")
    return "APPROVED", reasons


def _build_report(results: dict, verdict: Verdict, reasons: List[str]) -> str:
    ocr: dict = results.get("ocr", {})
    tamper: dict = results.get("tampering", {})
    bio: dict = results.get("biometric", {})
    deepfake: dict = results.get("deepfake", {})

    lines: List[str] = [
        "# Forensic Analysis Report",
        f"**Verdict:** {verdict}",
        "",
        "## Document",
        f"- Type: {ocr.get('id_type', 'Unknown')}",
        f"- OCR/MRZ confidence: {ocr.get('confidence', 0):.0f}%",
        f"- Format valid: {ocr.get('format_valid', False)}",
        "",
        "## Deepfake / AI-Generation Check",
    ]

    if deepfake and "confidence" in deepfake:
        df_conf = deepfake["confidence"]
        if df_conf > config.DEEPFAKE_REJECT_THRESHOLD:
            verdict_label = "AI-GENERATED (REJECTED)"
        elif df_conf > config.DEEPFAKE_REVIEW_THRESHOLD:
            verdict_label = "SUSPICIOUS (MANUAL REVIEW)"
        else:
            verdict_label = "REAL"
        lines.append(f"- Result: **{verdict_label}**")
        lines.append(f"- AI possibility: {df_conf:.1f}%")
        if deepfake.get("model_name"):
            lines.append(f"- Primary model: `{deepfake['model_name']}`")
        if deepfake.get("signals"):
            lines.append("- Signal breakdown:")
            signal_labels = {
                "neural_detector":    f"Neural Model ({config.DEEPFAKE_MODEL_NAME})",
                "texture_uniformity": "Face Texture Uniformity",
                "fft_score":          "FFT Frequency Smoothness",
                "skin_uniformity":    "YCbCr Skin Tone Uniformity",
                "symmetry_score":     "Facial Landmark Symmetry",
            }
            for sig_key, sig_val in deepfake["signals"].items():
                label = signal_labels.get(sig_key, sig_key)
                lines.append(f"  - {label}: {sig_val:.1f}/100")
    elif deepfake.get("error"):
        lines.append(f"- Detection skipped: {deepfake['error']}")
    else:
        lines.append("- Not performed")


    lines += [
        "",
        "## Tampering Check",
        f"- Integrity: {tamper.get('integrity_status', 'Unknown')}",
        f"- Flagged zones: {', '.join(tamper.get('flagged_zones', [])) or 'None'}",
        "",
        "## Biometric",
    ]

    if bio and "match_confidence" in bio:
        lines.append(f"- Match confidence: {bio['match_confidence']:.1f}%")
    else:
        lines.append("- Skipped or Blocked")

    lines += ["", "## Reasoning", *[f"- {r}" for r in reasons]]
    return "\n".join(lines)