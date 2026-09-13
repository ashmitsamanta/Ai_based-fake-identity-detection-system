import React, { useState } from 'react';

export default function OcrInspector({ ocr }) {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState('fields'); // 'fields' or 'raw'

  if (!ocr) return null;

  const fields = ocr.fields || {};
  const rawText = ocr.raw_text || '';
  const entries = Object.entries(fields).filter(([_, v]) => Boolean(v));

  const copyRawText = () => {
    if (!rawText) return;
    navigator.clipboard.writeText(rawText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatKey = (key) => {
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (l) => l.toUpperCase());
  };

  return (
    <div className="glass-panel detail-card animate-fade-in">
      <div className="detail-card-header">
        <div className="detail-header-left">
          <span className="detail-icon">📝</span>
          <div>
            <h3>Document Text Extraction &amp; OCR Inspection</h3>
            <p>
              Tesseract OCR Engine + PassportEye MRZ checksum parser
            </p>
          </div>
        </div>
        <div className="detail-header-right">
          <div className="mode-toggle">
            <button
              className={`toggle-btn ${activeTab === 'fields' ? 'active' : ''}`}
              onClick={() => setActiveTab('fields')}
            >
              Extracted Fields ({entries.length})
            </button>
            <button
              className={`toggle-btn ${activeTab === 'raw' ? 'active' : ''}`}
              onClick={() => setActiveTab('raw')}
            >
              Raw OCR Dump
            </button>
          </div>
        </div>
      </div>

      {/* Cryptographic Checksum Banner */}
      {ocr.validation_reasons && ocr.validation_reasons.length > 0 && (
        <div
          className={`checksum-banner ${ocr.format_valid ? 'banner-success' : 'banner-danger'}`}
          style={{
            margin: '0 0 16px 0',
            padding: '12px 16px',
            borderRadius: '8px',
            background: ocr.format_valid ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
            border: `1px solid ${ocr.format_valid ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)'}`,
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: '6px', color: ocr.format_valid ? '#34d399' : '#f87171' }}>
            {ocr.format_valid ? '✓ Document Format & Checksum Verified' : '⚠️ Format / Validation Failure (Counterfeit or Invalid ID)'}
          </div>
          <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '0.875rem', color: '#e2e8f0', lineHeight: 1.5 }}>
            {ocr.validation_reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {activeTab === 'fields' ? (
        <div className="ocr-fields-grid">
          {entries.length > 0 ? (
            entries.map(([key, val]) => (
              <div key={key} className="ocr-field-card">
                <span className="field-label">{formatKey(key)}</span>
                <span className="field-value" title={String(val)}>{String(val)}</span>
              </div>
            ))
          ) : (
            <div className="empty-fields-notice">
              <span>⚠️ No structured identity fields could be parsed automatically.</span>
              <p>Check the raw OCR tab to review recognized text strings.</p>
            </div>
          )}
        </div>
      ) : (
        <div className="raw-ocr-container">
          <div className="raw-toolbar">
            <span className="raw-info">Word Confidence: {Math.round(ocr.confidence || 0)}%</span>
            <button className="btn-copy" onClick={copyRawText}>
              {copied ? '✓ Copied' : '📋 Copy Text'}
            </button>
          </div>
          <pre className="raw-ocr-text">
            {rawText || '// No text extracted from document.'}
          </pre>
        </div>
      )}
    </div>
  );
}
