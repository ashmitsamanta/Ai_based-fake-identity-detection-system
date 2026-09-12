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
