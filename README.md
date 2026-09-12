# 🔍 Forensic Document Inspector — SIH26188

**AI-Based Fake Identity & Document Screening System**
Ministry of Home Affairs | Blockchain & Cybersecurity

A modern FastAPI and React-powered forensic analysis system that screens Indian identity and travel
documents for forgery, data manipulation, deepfake photo injection, and identity fraud —
using InsightFace biometrics, a custom SigLIP deepfake detector, Tesseract OCR / MRZ parsing,
Error Level Analysis, and EXIF metadata inspection.

---

## Architecture

```
Browser (React SPA — Vite)
  │ (Live Webcam, Drag-Drop, Real-time 5-Stage Stepper, Confetti)
  ▼
┌────────────────────────────────────────────────────────┐
│  FastAPI Backend Server (server.py on port 8000)       │
│  - SSE Streaming endpoint (/api/analyze)               │
│  - Health status & config constants (/api/health)      │
│  - Serves compiled React production build              │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  agent/forensic_agent.py  — run_analysis() generator          │
│                                                                │
│  Step 1 ▶ Biometric Gatekeeper (agent/face_engine.py)         │
│           InsightFace buffalo_l, cosine similarity             │
│           < 50%  → REJECT immediately                         │
│                                                                │
│  Step 2 ▶ Deepfake / AI-Generation Check                      │
│           (agent/deepfake_detector.py)                         │
│           Neural SigLIP Model (prithivMLmods/deepfake-detector │
│           -model-v1) + 4 CV signals (texture, FFT, skin, sym)  │
│           > 80% AI possibility → REJECT (AI Generated)         │
│           > 66% AI possibility → MANUAL REVIEW (Suspicious)    │
│                                                                │
│  Step 3 ▶ OCR / MRZ Extraction                                │
│           pytesseract + passporteye (passport MRZ)            │
│           Regex matching for Aadhaar, PAN, Voter ID            │
│                                                                │
│  Step 4 ▶ Tampering Detection                                  │
│           Error Level Analysis (ELA) + EXIF metadata check    │
│                                                                │
│  Step 5 ▶ Verdict  (deterministic decision matrix)             │
│           → APPROVED / REJECT / MANUAL REVIEW                 │
└────────────────────────────────────────────────────────────────┘
```

### Decision Matrix

| Condition | Verdict |
|---|---|
| Biometric match < 50%, OR AI possibility > 80% (AI Generated), OR tampering in critical field, OR document format/checksum invalid | **REJECT** |
| AI possibility > 66% (Suspicious), OR OCR/MRZ confidence too low, OR biometric match is 50–60% | **MANUAL REVIEW** |
| All checks pass, AI possibility ≤ 66%, biometric match > 60%, no tampering | **APPROVED** |

---

## Project Structure

```
├── backend/                # FastAPI Backend Service & Forensic Analysis Engine
│   ├── server.py           # ← FastAPI backend entry point & static SPA host
│   ├── config.py           # Thresholds, regex patterns, and filesystem paths
│   ├── requirements.txt    # Python backend dependencies
│   ├── temp_uploads/       # Transient — auto-wiped after every analysis run
│   ├── agent/              # Forensic analysis pipeline (strictly preserved)
│   │   ├── __init__.py     # Public API re-exports (run_analysis + TypedDicts)
│   │   ├── forensic_agent.py # Pipeline orchestrator — run_analysis() generator
│   │   ├── face_engine.py  # InsightFace biometric engine (buffalo_l model)
│   │   ├── deepfake_detector.py # Multi-signal AI-generation / deepfake detector
│   │   └── types.py        # TypedDict data contracts for every pipeline stage
│   └── utils/              # General-purpose helpers
│       ├── __init__.py
│       └── image_utils.py  # Temp file save / validate / cleanup
│
├── frontend/               # Modern React.js (Vite) Single Page Application
│   ├── index.html
│   ├── vite.config.js
│   ├── package.json
│   ├── dist/               # Production build served by FastAPI
│   └── src/
│       ├── main.jsx
│       ├── App.jsx         # SSE streaming client & orchestration
│       ├── index.css       # Cyber-forensic design tokens
│       ├── App.css         # Glassmorphism & micro-animations
│       └── components/     # Modular React components
│           ├── Header.jsx
│           ├── UploadSection.jsx
│           ├── PipelineStepper.jsx
│           ├── VerdictBadge.jsx
│           ├── MetricsRow.jsx
│           ├── DeepfakeBreakdown.jsx
│           ├── ElaComparison.jsx
│           ├── OcrInspector.jsx
│           └── ReportViewer.jsx
│
├── Dockerfile              # Container deployment recipe
├── run_dev.bat             # Concurrent Dev Launcher (FastAPI + Vite Hot Reload)
├── run_system.bat          # Single-click launcher for Windows
└── README.md
```

---

## Quick Start

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | |
| Node.js 18+ | Automatically portable or via winget |
| Tesseract OCR binary | See install notes below |
| InsightFace model pack | Downloaded automatically on first run |

### Run

**Production / Single Command:**
```bash
cd backend
python server.py
# Or on Windows, double-click: run_system.bat
```
The dashboard opens at **http://localhost:8000**.

**Full Development Mode (Hot-Reloading React):**
```bash
# Terminal 1: Backend
cd backend
python server.py

# Terminal 2: React Frontend
cd frontend
npm run dev
```
The Vite dev server opens at **http://localhost:5173**.

> **Note:** InsightFace downloads the `buffalo_l` model pack (~200 MB) on the very
> first run. Subsequent runs load from the local cache.

---

## Configuration

All tunable parameters live in [`backend/config.py`](backend/config.py):

| Constant | Default | Description |
|---|---|---|
| `OCR_CONFIDENCE_THRESHOLD` | `40.0` | Minimum Tesseract OCR confidence (%) |
| `BIOMETRIC_REJECT_THRESHOLD` | `50.0` | Biometric match below this → REJECT |
| `BIOMETRIC_REVIEW_THRESHOLD` | `60.0` | Biometric match between 50–60% → MANUAL REVIEW |
| `DEEPFAKE_REJECT_THRESHOLD` | `95.0` | AI-generation confidence above this → REJECT |
| `DEEPFAKE_REVIEW_THRESHOLD` | `5.0` | AI-generation confidence above this → flag for review |
| `ELA_QUALITY` | `90` | JPEG re-compression quality for ELA |
| `ELA_SENSITIVITY` | `25` | Per-pixel threshold for ELA anomaly detection |
| `ELA_SCALE_FACTOR` | `15` | ELA heatmap amplification factor |

**Deepfake signal weights** (must sum to 1.0):

| Signal | Weight | What it measures |
|---|---|---|
| `texture_uniformity` | 0.40 | Sharpness uniformity across face regions |
| `fft_score` | 0.25 | High-frequency noise deficit (FFT) |
| `skin_uniformity` | 0.20 | Chrominance variation in skin (YCbCr) |
| `symmetry_score` | 0.15 | Facial landmark horizontal symmetry |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite (SPA with Cyber-Forensic Glassmorphic UI) |
| Backend API | FastAPI + Server-Sent Events (SSE) streaming |
| Biometrics | InsightFace (buffalo_l model pack, cosine similarity) |
| Deepfake Detection | SigLIP Neural Model (prithivMLmods/deepfake-detector-model-v1) + CV ensemble |
| OCR | Tesseract (pytesseract) + passporteye (passport MRZ) |
| Tampering Detection | PIL Error Level Analysis (ELA) + EXIF inspection |
| Language & Runtime | Python 3.10+ & Node.js 18+ |

---

## License

Developed for **Smart India Hackathon 2026** — Problem Statement **SIH26188**.
