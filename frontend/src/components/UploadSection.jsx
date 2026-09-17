import React, { useState, useRef, useEffect } from 'react';

export default function UploadSection({
  idFile,
  setIdFile,
  selfieFile,
  setSelfieFile,
  selfieDataUrl,
  setSelfieDataUrl,
  onAnalyze,
  isAnalyzing,
}) {
  const [selfieMode, setSelfieMode] = useState('camera'); // 'camera' or 'upload'
  const [isCameraActive, setIsCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [isDraggingId, setIsDraggingId] = useState(false);
  const [validationError, setValidationError] = useState(null);

  const [idPreviewUrl, setIdPreviewUrl] = useState(null);
  const [selfiePreviewUrl, setSelfiePreviewUrl] = useState(null);

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const canvasRef = useRef(null);
  const idInputRef = useRef(null);
  const selfieInputRef = useRef(null);

  // Manage id preview URL lifecycle with cleanup
  useEffect(() => {
    if (!idFile) {
      setIdPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(idFile);
    setIdPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [idFile]);

  // Manage selfie preview URL lifecycle with cleanup
  useEffect(() => {
    if (!selfieFile) {
      setSelfiePreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(selfieFile);
    setSelfiePreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [selfieFile]);

  // Start Camera Feed
  const startCamera = async () => {
    setCameraError(null);
    try {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
      }
      setIsCameraActive(true);
    } catch (err) {
      console.warn('Camera access denied or unavailable:', err);
      setCameraError('Camera access unavailable. You can upload a selfie image below.');
      setSelfieMode('upload');
      setIsCameraActive(false);
    }
  };

  // Stop Camera & free hardware
  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setIsCameraActive(false);
  };

  // Turn off camera when analyzing to conserve GPU/CPU, or toggle on/off with mode
  useEffect(() => {
    if (isAnalyzing) {
      stopCamera();
    } else if (selfieMode === 'camera' && !selfieDataUrl) {
      startCamera();
    } else {
      stopCamera();
    }
    return () => stopCamera();
  }, [selfieMode, selfieDataUrl, isAnalyzing]);

  // Support pasting images from clipboard (e.g. Ctrl+V)
  useEffect(() => {
    const handlePaste = (e) => {
      if (e.clipboardData && e.clipboardData.items) {
        for (let i = 0; i < e.clipboardData.items.length; i++) {
          const item = e.clipboardData.items[i];
          if (item.type && item.type.startsWith('image/')) {
            const blob = item.getAsFile();
            if (blob) {
              handleIdFile(blob);
              break;
            }
          }
        }
      }
    };
    window.addEventListener('paste', handlePaste);
    return () => window.removeEventListener('paste', handlePaste);
  }, []);

  // Capture Selfie from Webcam
  const captureSelfie = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;

    const ctx = canvas.getContext('2d');
    // Mirror the capture for natural webcam feel
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
    setSelfieDataUrl(dataUrl);
    setSelfieFile(null);
    stopCamera();
  };

  // Retake Selfie
  const retakeSelfie = () => {
    setSelfieDataUrl(null);
    setSelfieFile(null);
    startCamera();
  };

  const MAX_FILE_BYTES = 15 * 1024 * 1024; // 15MB limit

  // Handle ID File Selection with validation
  const handleIdFile = (file) => {
    setValidationError(null);
    if (!file) return;
    if (!file.type || !file.type.startsWith('image/')) {
      setValidationError('Invalid document format. Please upload an image (JPG, PNG, WEBP, BMP).');
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setValidationError('Document file size exceeds the 15 MB limit. Please select a smaller file.');
      return;
    }
    setIdFile(file);
  };

  const handleSelfieUpload = (file) => {
    setValidationError(null);
    if (!file) return;
    if (!file.type || !file.type.startsWith('image/')) {
      setValidationError('Invalid selfie format. Please upload an image file.');
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setValidationError('Selfie file size exceeds the 15 MB limit.');
      return;
    }
    setSelfieFile(file);
    setSelfieDataUrl(null);
  };

  // Handle ID Drag & Drop
  const onDragOver = (e) => {
    e.preventDefault();
    setIsDraggingId(true);
  };

  const onDragLeave = () => {
    setIsDraggingId(false);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setIsDraggingId(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleIdFile(e.dataTransfer.files[0]);
    }
  };

  const hasSelfie = Boolean(selfieDataUrl || selfieFile);
  const canAnalyze = Boolean(idFile && !isAnalyzing);
  const isDocOnly = Boolean(idFile && !hasSelfie);

  return (
    <div className="upload-container">
      {validationError && (
        <div className="glass-panel" style={{
          margin: '0 0 16px 0',
          padding: '12px 18px',
          borderRadius: '10px',
          background: 'rgba(239, 68, 68, 0.12)',
          border: '1px solid rgba(239, 68, 68, 0.4)',
          color: '#f87171',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <span>⚠️ {validationError}</span>
          <button
            onClick={() => setValidationError(null)}
            style={{
              background: 'none',
              border: 'none',
              color: '#f87171',
              cursor: 'pointer',
              fontWeight: 'bold',
              fontSize: '1rem',
            }}
          >
            ✕
          </button>
        </div>
      )}
      <div className="upload-grid">
        {/* Document Upload Card */}
        <div className="glass-panel upload-card">
          <div className="upload-card-header">
            <div className="card-badge">Step 1</div>
            <h3>📄 Identity / Travel Document</h3>
            <p>Upload a Passport, Visa, Aadhaar, PAN, Voter ID, or Permit (JPG, PNG, WEBP)</p>
          </div>

          <div
            className={`dropzone ${isDraggingId ? 'dropzone-active' : ''} ${idFile ? 'has-file' : ''}`}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => !idFile && idInputRef.current?.click()}
          >
            <input
              type="file"
              ref={idInputRef}
              style={{ display: 'none' }}
              accept="image/*,.jpg,.jpeg,.png,.webp,.bmp"
              onChange={(e) => handleIdFile(e.target.files?.[0])}
            />

            {idFile ? (
              <div className="preview-box">
                <img
                  src={idPreviewUrl || ''}
                  alt="Uploaded ID Document"
                  className="preview-img"
                />
                <div className="preview-overlay">
                  <div className="file-info">
                    <span className="file-name">{idFile.name}</span>
                    <span className="file-size">{(idFile.size / 1024).toFixed(1)} KB</span>
                  </div>
                  <button
                    className="btn-remove"
                    onClick={(e) => {
                      e.stopPropagation();
                      setIdFile(null);
                    }}
                    title="Remove and choose another document"
                  >
                    ✕ Remove
                  </button>
                </div>
              </div>
            ) : (
              <div className="dropzone-placeholder">
                <div className="upload-icon-circle">📁</div>
                <h4>Drag &amp; drop document here</h4>
                <p>or click to browse from device</p>
                <div className="supported-badges">
                  <span>Passport</span>
                  <span>Aadhaar</span>
                  <span>PAN</span>
                  <span>Voter ID</span>
                  <span>Permit</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Live Selfie Gatekeeper Card */}
        <div className="glass-panel upload-card">
          <div className="upload-card-header">
            <div className="card-badge">Step 2</div>
            <div className="header-tabs-row">
              <h3>📸 Live Selfie Gatekeeper</h3>
              <div className="mode-toggle">
                <button
                  className={`toggle-btn ${selfieMode === 'camera' ? 'active' : ''}`}
                  onClick={() => setSelfieMode('camera')}
                  disabled={isAnalyzing}
                >
                  Webcam
                </button>
                <button
                  className={`toggle-btn ${selfieMode === 'upload' ? 'active' : ''}`}
                  onClick={() => setSelfieMode('upload')}
                  disabled={isAnalyzing}
                >
                  Upload
                </button>
              </div>
            </div>
            <p>Biometric face match must be &gt;50% to pass the Fast-Fail Gatekeeper</p>
          </div>

          <div className="selfie-area">
            {selfieMode === 'camera' ? (
              <div className="camera-box">
                {selfieDataUrl ? (
                  <div className="preview-box">
                    <img src={selfieDataUrl} alt="Captured Selfie" className="preview-img mirrored" />
                    <div className="preview-overlay">
                      <span className="badge badge-success">Selfie Captured</span>
                      <button className="btn-secondary" onClick={retakeSelfie} disabled={isAnalyzing}>
                        🔄 Retake
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="webcam-viewport">
                    <video ref={videoRef} autoPlay playsInline muted className="webcam-video mirrored" />
                    <div className="face-guide-oval">
                      <div className="targeting-crosshair top-left"></div>
                      <div className="targeting-crosshair top-right"></div>
                      <div className="targeting-crosshair bottom-left"></div>
                      <div className="targeting-crosshair bottom-right"></div>
                      <span className="guide-label">Align Face Inside Oval</span>
                    </div>

                    <div className="camera-controls">
                      <button
                        className="btn-capture"
                        onClick={captureSelfie}
                        disabled={!isCameraActive || isAnalyzing}
                      >
                        <span className="shutter-circle"></span>
                        Capture Photo
                      </button>
                    </div>
                  </div>
                )}
                <canvas ref={canvasRef} style={{ display: 'none' }} />
              </div>
            ) : (
              <div
                className={`dropzone ${selfieFile ? 'has-file' : ''}`}
                onClick={() => !selfieFile && selfieInputRef.current?.click()}
              >
                <input
                  type="file"
                  ref={selfieInputRef}
                  style={{ display: 'none' }}
                  accept="image/*"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleSelfieUpload(f);
                  }}
                />
                {selfieFile ? (
                  <div className="preview-box">
                    <img
                      src={selfiePreviewUrl || ''}
                      alt="Uploaded Selfie"
                      className="preview-img"
                    />
                    <div className="preview-overlay">
                      <span className="file-name">{selfieFile.name}</span>
                      <button
                        className="btn-remove"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelfieFile(null);
                        }}
                      >
                        ✕ Remove
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="dropzone-placeholder">
                    <div className="upload-icon-circle">👤</div>
                    <h4>Upload a recent selfie photo</h4>
                    <p>Clear frontal portrait for face verification</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Action Trigger Bar */}
      <div className="action-bar glass-panel">
        <div className="action-status">
          <div className={`status-indicator ${canAnalyze ? 'ready' : ''}`}></div>
          <span>
            {canAnalyze
              ? isDocOnly
                ? 'Document-Only Screening Ready: Document format validation, AI deepfake analysis & ELA tampering detection.'
                : 'Full Verification Ready: Biometric Face Gatekeeper + Format Validation + Deepfake + ELA Tampering.'
              : 'Please upload an ID document image (Aadhaar, PAN, Passport, Voter ID) to start screening.'}
          </span>
        </div>

        <button
          className="btn-primary btn-launch"
          onClick={onAnalyze}
          disabled={!canAnalyze}
          id="btn-run-analysis"
        >
          {isAnalyzing ? (
            <>
              <span className="spinner"></span>
              Screening Document...
            </>
          ) : isDocOnly ? (
            <>
              <span>🔍</span>
              Screen Document (Document-Only)
            </>
          ) : (
            <>
              <span>🚀</span>
              Run Full Verification (ID + Selfie)
            </>
          )}
        </button>
      </div>
    </div>
  );
}
