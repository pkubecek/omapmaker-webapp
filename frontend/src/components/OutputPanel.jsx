import React, { useEffect, useRef, useState } from 'react';
import { getPngUrl, getGpkgUrl } from '../api';

const S = {
  panel: {
    width: 288,
    flexShrink: 0,
    background: 'var(--panel-bg)',
    borderLeft: '0.5px solid var(--panel-border)',
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
  },
  section: {
    padding: '14px 16px',
    borderBottom: '0.5px solid var(--panel-border)',
  },
  sectionLabel: {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    fontWeight: 500,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--text-secondary)',
    marginBottom: 10,
  },
  progressHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  progressTitle: { fontSize: 12, fontWeight: 500 },
  progressPct: { fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-secondary)' },
  barWrap: {
    background: '#f0ead6',
    borderRadius: 3,
    height: 4,
    overflow: 'hidden',
    marginBottom: 6,
  },
  barFill: {
    height: '100%',
    borderRadius: 3,
    background: 'var(--forest)',
    transition: 'width 0.5s ease',
  },
  barFillError: { background: '#c96a3a' },
  stepText: {
    fontFamily: 'var(--mono)',
    fontSize: 11,
    color: 'var(--text-secondary)',
  },
  logWrap: {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    lineHeight: 1.8,
    maxHeight: 220,
    overflowY: 'auto',
    color: 'var(--text-secondary)',
  },
  logLine: { display: 'flex', gap: 6, alignItems: 'baseline' },
  logTime: { color: 'var(--text-muted)', flexShrink: 0, fontSize: 9 },
  logOk: { color: 'var(--forest)' },
  logWarn: { color: 'var(--rock)' },
  logInfo: { color: 'var(--text-secondary)' },
  outputSection: { padding: '14px 16px', flex: 1 },
  previewWrap: {
    borderRadius: 'var(--radius-md)',
    overflow: 'hidden',
    border: '0.5px solid var(--panel-border)',
    marginBottom: 10,
    aspectRatio: '1.414',
    background: 'var(--paper)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  previewImg: { width: '100%', height: '100%', objectFit: 'cover', display: 'block' },
  previewPlaceholder: { textAlign: 'center', color: 'var(--text-muted)', padding: 16 },
  placeholderIcon: { fontSize: 28, marginBottom: 6, opacity: 0.3 },
  placeholderText: { fontSize: 11, lineHeight: 1.4 },
  dlBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    width: '100%',
    padding: '8px 0',
    borderRadius: 'var(--radius-md)',
    fontSize: 12,
    cursor: 'pointer',
    marginBottom: 6,
    border: '0.5px solid var(--panel-border)',
    background: 'none',
    color: 'var(--text-primary)',
    fontFamily: 'var(--sans)',
    transition: 'background 0.15s',
  },
  dlBtnPrimary: {
    background: 'var(--ink)',
    color: '#fff',
    borderColor: 'var(--ink)',
  },
  dlBtnDisabled: { opacity: 0.38, cursor: 'not-allowed' },
};

// Tlačítko Generovat mapu
function RunBtn({ disabled, onClick, children }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        width: '100%', padding: '9px 0',
        borderRadius: 'var(--radius-md)', border: 'none',
        background: disabled ? 'var(--panel-border)' : hovered ? '#c05a2a' : 'var(--rock)',
        color: disabled ? 'var(--text-muted)' : '#fff',
        fontSize: 12, fontFamily: 'var(--sans)', fontWeight: 500,
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'background 0.15s',
        letterSpacing: '0.02em',
      }}
    >
      {children}
    </button>
  );
}

// Tlačítko se stažením + hover efekt
function DlBtn({ href, download, disabled, primary, children }) {
  const [hovered, setHovered] = useState(false);

  const baseStyle = {
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
    width: '100%', padding: '8px 0', borderRadius: 'var(--radius-md)',
    fontSize: 12, cursor: disabled ? 'not-allowed' : 'pointer',
    marginBottom: 6, fontFamily: 'var(--sans)', textDecoration: 'none',
    border: '0.5px solid var(--panel-border)',
    transition: 'background 0.15s, border-color 0.15s, opacity 0.15s',
    opacity: disabled ? 0.38 : 1,
    ...(primary ? {
      background: hovered && !disabled ? '#2d3448' : 'var(--ink)',
      color: '#fff',
      borderColor: 'var(--ink)',
    } : {
      background: hovered && !disabled ? 'var(--color-background-secondary, #f5f4f0)' : 'none',
      color: 'var(--text-primary)',
    }),
  };

  if (disabled) {
    return <button style={baseStyle} disabled>{children}</button>;
  }

  return (
    <a
      href={href}
      download={download}
      style={baseStyle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {children}
    </a>
  );
}

const STATUS_LABELS = {
  idle: 'Čeká na spuštění',
  queued: 'Ve frontě...',
  running: 'Zpracovávám...',
  done: 'Hotovo ✓',
  error: 'Chyba!',
};

export default function OutputPanel({ job, logLines, canRun, running, onRun, isMobile }) {
  const logRef = useRef(null);
  const [lightbox, setLightbox] = useState(false);
  const { status = 'idle', progress = 0, step = '', jobId = null } = job || {};
  const isDone = status === 'done';
  const isError = status === 'error';

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logLines]);

  // Zavření lightboxu klávesou Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') setLightbox(false); };
    if (lightbox) window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [lightbox]);

  const panelStyle = {
    ...S.panel,
    width: isMobile ? '100%' : 'clamp(240px, 20vw, 320px)',
  };

  const now = () => {
    const d = new Date();
    return [d.getHours(), d.getMinutes(), d.getSeconds()]
      .map((n) => String(n).padStart(2, '0'))
      .join(':');
  };

  return (
    <div style={panelStyle}>
      {/* Generovat mapu */}
      <div style={{ padding: '12px 16px', borderBottom: '0.5px solid var(--panel-border)' }}>
        <RunBtn disabled={!canRun || running} onClick={onRun}>
          {running ? '⏳ Zpracovávám...' : '▶ Generovat mapu'}
        </RunBtn>
        {!canRun && !running && (
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--mono)', marginTop: 5, textAlign: 'center' }}>
            Nahrajte DMR a DMP
          </div>
        )}
      </div>

      {/* Progress */}
      <div style={S.section}>
        <div style={S.sectionLabel}>Průběh zpracování</div>
        <div style={S.progressHeader}>
          <span style={S.progressTitle}>{STATUS_LABELS[status] || status}</span>
          <span style={S.progressPct}>{status === 'idle' ? '—' : `${Math.round(progress)}%`}</span>
        </div>
        <div style={S.barWrap}>
          <div
            style={{
              ...S.barFill,
              ...(isError ? S.barFillError : {}),
              width: `${progress}%`,
            }}
          />
        </div>
        <div style={S.stepText}>
          {status === 'idle'
            ? 'Nahrajte DMR a DMP, pak klikněte Generovat mapu'
            : step || '—'}
        </div>
      </div>

      {/* Log */}
      <div style={S.section}>
        <div style={S.sectionLabel}>Log</div>
        <div style={S.logWrap} ref={logRef}>
          {logLines.length === 0 && (
            <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>Zde se zobrazí průběh...</span>
          )}
          {logLines.map((line, i) => (
            <div style={S.logLine} key={i}>
              <span style={S.logTime}>{line.time}</span>
              <span style={line.type === 'ok' ? S.logOk : line.type === 'warn' ? S.logWarn : S.logInfo}>
                {line.msg}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Output */}
      <div style={S.outputSection}>
        <div style={S.sectionLabel}>Výstup</div>
        <div
          style={{ ...S.previewWrap, cursor: isDone && jobId ? 'zoom-in' : 'default' }}
          onClick={() => isDone && jobId && setLightbox(true)}
          title={isDone && jobId ? 'Kliknutím zvětšit' : undefined}
        >
          {isDone && jobId ? (
            <>
              <img
                style={S.previewImg}
                src={getPngUrl(jobId)}
                alt="Náhled vygenerované mapy"
                onError={(e) => { e.target.style.display = 'none'; }}
              />
              <div style={{
                position: 'absolute', bottom: 6, right: 6,
                background: 'rgba(0,0,0,0.45)', borderRadius: 4,
                padding: '2px 5px', fontSize: 11, color: '#fff', pointerEvents: 'none',
              }}>⛶</div>
            </>
          ) : (
            <div style={S.previewPlaceholder}>
              <div style={S.placeholderIcon}>🗺</div>
              <div style={S.placeholderText}>
                {isError ? 'Zpracování selhalo' : 'Výsledná mapa se zobrazí zde'}
              </div>
            </div>
          )}
        </div>

        {/* Lightbox */}
        {lightbox && (
          <div
            onClick={() => setLightbox(false)}
            style={{
              position: 'fixed', inset: 0, zIndex: 1000,
              background: 'rgba(0,0,0,0.82)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'zoom-out',
            }}
          >
            <img
              src={getPngUrl(jobId)}
              alt="Mapa"
              style={{
                maxWidth: '92vw', maxHeight: '92vh',
                objectFit: 'contain', borderRadius: 4,
                boxShadow: '0 8px 40px rgba(0,0,0,0.6)',
              }}
              onClick={(e) => e.stopPropagation()}
            />
            <button
              onClick={() => setLightbox(false)}
              style={{
                position: 'fixed', top: 18, right: 22,
                background: 'none', border: 'none', color: '#fff',
                fontSize: 28, cursor: 'pointer', lineHeight: 1,
                opacity: 0.8,
              }}
            >×</button>
          </div>
        )}

        <DlBtn href={isDone && jobId ? getPngUrl(jobId) : undefined}
          download="OMap.png" disabled={!isDone} primary>
          ↓ Stáhnout mapu v PNG
        </DlBtn>

        <DlBtn href={isDone && jobId ? getGpkgUrl(jobId) : undefined}
          download="OMap.gpkg" disabled={!isDone}>
          ↓ Exportovat GPKG pro OpenOrienteerinMapper
        </DlBtn>

        <DlBtn href={`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/api/crt/OMapMaker-OpenOrienteeringMapper.crt`}
          download="OMapMaker-OpenOrienteeringMapper.crt">
          ↓ Stáhnout CRT soubor
        </DlBtn>
      </div>
    </div>
  );
}
