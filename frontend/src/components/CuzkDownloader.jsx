import React, { useState, useEffect, useRef } from 'react';
import L from 'leaflet';

const S = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(26,31,46,0.55)',
    zIndex: 9000,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  modal: {
    background: 'var(--panel-bg)',
    borderRadius: 'var(--radius-lg)',
    border: '0.5px solid var(--panel-border)',
    width: 760,
    maxWidth: '95vw',
    maxHeight: '90vh',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    boxShadow: '0 8px 40px rgba(0,0,0,0.18)',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '14px 20px',
    borderBottom: '0.5px solid var(--panel-border)',
    background: 'var(--ink)',
    color: '#fff',
  },
  headerTitle: { fontFamily: 'var(--mono)', fontSize: 13, fontWeight: 500, letterSpacing: '0.04em' },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#fff',
    fontSize: 18,
    cursor: 'pointer',
    opacity: 0.6,
    lineHeight: 1,
  },
  body: { display: 'flex', flex: 1, overflow: 'hidden' },
  mapWrap: { flex: 1, position: 'relative', minHeight: 400 },
  sidebar: {
    width: 220,
    flexShrink: 0,
    borderLeft: '0.5px solid var(--panel-border)',
    padding: 16,
    display: 'flex',
    flexDirection: 'column',
    gap: 14,
    overflowY: 'auto',
  },
  sLabel: {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    fontWeight: 500,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--text-secondary)',
    marginBottom: 6,
  },
  radio: { display: 'flex', flexDirection: 'column', gap: 6 },
  radioLabel: { display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, cursor: 'pointer' },
  dirRow: { display: 'flex', gap: 6 },
  dirInput: {
    flex: 1,
    fontFamily: 'var(--mono)',
    fontSize: 11,
    padding: '5px 8px',
    border: '0.5px solid var(--panel-border)',
    borderRadius: 'var(--radius-sm)',
    background: '#fafaf8',
  },
  barWrap: {
    background: '#f0ead6',
    borderRadius: 3,
    height: 5,
    overflow: 'hidden',
    marginBottom: 4,
  },
  barFill: { height: '100%', borderRadius: 3, background: 'var(--forest)', transition: 'width 0.4s' },
  dlBtn: {
    marginTop: 'auto',
    padding: '9px 0',
    borderRadius: 'var(--radius-md)',
    border: 'none',
    background: 'var(--rock)',
    color: '#fff',
    fontSize: 12,
    fontFamily: 'var(--sans)',
    cursor: 'pointer',
    fontWeight: 500,
    transition: 'background 0.15s',
  },
  dlBtnDisabled: { background: 'var(--panel-border)', color: 'var(--text-muted)', cursor: 'not-allowed' },
  hint: {
    position: 'absolute',
    bottom: 10,
    left: '50%',
    transform: 'translateX(-50%)',
    background: 'rgba(26,31,46,0.8)',
    color: '#fff',
    fontFamily: 'var(--mono)',
    fontSize: 10,
    padding: '4px 12px',
    borderRadius: 14,
    pointerEvents: 'none',
    whiteSpace: 'nowrap',
    zIndex: 500,
  },
  footer: {
    padding: '10px 20px',
    borderTop: '0.5px solid var(--panel-border)',
    fontFamily: 'var(--mono)',
    fontSize: 10,
    color: 'var(--text-secondary)',
    minHeight: 32,
  },
};

export default function CuzkDownloader({ onComplete, onClose }) {
  const mapRef = useRef(null);
  const leafletRef = useRef(null);
  const rectRef = useRef(null);
  const [dsmType, setDsmType] = useState('DMPOK');
  const [outDir, setOutDir] = useState('./cuzk_data');
  const [bbox, setBbox] = useState(null);
  const [progress, setProgress] = useState(0);
  const [progMsg, setProgMsg] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [statusMsg, setStatusMsg] = useState('Vyberte oblast táhnutím myši.');

  useEffect(() => {
    if (leafletRef.current) return;
    const map = L.map(mapRef.current, { center: [49.8, 15.5], zoom: 7, zoomControl: true });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap', maxZoom: 19,
    }).addTo(map);

    let startLl = null, tmpRect = null;
    map.on('mousedown', (e) => {
      startLl = e.latlng;
      if (rectRef.current) { rectRef.current.remove(); rectRef.current = null; }
      setBbox(null);
    });
    map.on('mousemove', (e) => {
      if (!startLl) return;
      if (tmpRect) tmpRect.remove();
      tmpRect = L.rectangle([startLl, e.latlng], {
        color: '#c96a3a', weight: 1.5, dashArray: '5 3', fillOpacity: 0.06,
      }).addTo(map);
    });
    map.on('mouseup', (e) => {
      if (!startLl) return;
      if (tmpRect) { tmpRect.remove(); tmpRect = null; }
      const b = {
        min_lat: Math.min(startLl.lat, e.latlng.lat),
        max_lat: Math.max(startLl.lat, e.latlng.lat),
        min_lon: Math.min(startLl.lng, e.latlng.lng),
        max_lon: Math.max(startLl.lng, e.latlng.lng),
      };
      if (b.max_lat - b.min_lat < 0.005 || b.max_lon - b.min_lon < 0.005) { startLl = null; return; }
      rectRef.current = L.rectangle([[b.min_lat, b.min_lon], [b.max_lat, b.max_lon]], {
        color: '#c96a3a', weight: 2, dashArray: '6 4', fillOpacity: 0.07,
      }).addTo(map);
      setBbox(b);
      const kmLat = ((b.max_lat - b.min_lat) * 111).toFixed(1);
      const kmLon = ((b.max_lon - b.min_lon) * 111 * Math.cos((b.min_lat + b.max_lat) / 2 * Math.PI / 180)).toFixed(1);
      const est = Math.max(1, Math.round(kmLat / 2)) * Math.max(1, Math.round(kmLon / 2));
      setStatusMsg(`Oblast: ~${kmLat} × ${kmLon} km · odhadovaný počet dlaždic: ~${est * 2}`);
      startLl = null;
    });

    leafletRef.current = map;
    return () => { map.remove(); leafletRef.current = null; };
  }, []);

  const handleDownload = async () => {
    if (!bbox || downloading) return;
    setDownloading(true);
    setProgress(2);
    setProgMsg('Připojuji se k ČÚZK ATOM...');
    try {
      const { downloadCuzk } = await import('../api');
      setProgress(10);
      setProgMsg('Stahuji metadata dlaždic...');
      const result = await downloadCuzk(bbox, dsmType, outDir);
      setProgress(100);
      setProgMsg('Hotovo!');
      setTimeout(() => {
        onComplete(result.dmr_path, result.dmp_path);
        onClose();
      }, 800);
    } catch (err) {
      setProgMsg('Chyba: ' + (err.response?.data?.detail || err.message));
      setProgress(0);
      setDownloading(false);
    }
  };

  return (
    <div style={S.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={S.modal}>
        <div style={S.header}>
          <span style={S.headerTitle}>Stáhnout data z ČÚZK ATOM</span>
          <button style={S.closeBtn} onClick={onClose}>×</button>
        </div>

        <div style={S.body}>
          <div style={S.mapWrap}>
            <div ref={mapRef} style={{ width: '100%', height: '100%' }} />
            {!bbox && <div style={S.hint}>Táhněte myší pro výběr oblasti</div>}
          </div>

          <div style={S.sidebar}>
            <div>
              <div style={S.sLabel}>Model povrchu (DSM)</div>
              <div style={S.radio}>
                <label style={S.radioLabel}>
                  <input type="radio" name="dsm" value="DMPOK" checked={dsmType === 'DMPOK'}
                    onChange={() => setDsmType('DMPOK')} />
                  DMP OK (doporučeno)
                </label>
                <label style={S.radioLabel}>
                  <input type="radio" name="dsm" value="DMP1G" checked={dsmType === 'DMP1G'}
                    onChange={() => setDsmType('DMP1G')} />
                  DMP 1G
                </label>
              </div>
            </div>

            <div>
              <div style={S.sLabel}>Výstupní složka</div>
              <div style={S.dirRow}>
                <input style={S.dirInput} type="text" value={outDir}
                  onChange={(e) => setOutDir(e.target.value)}
                  placeholder="./cuzk_data" />
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4, fontFamily: 'var(--mono)' }}>
                Cesta na serveru
              </div>
            </div>

            {(progress > 0 || downloading) && (
              <div>
                <div style={S.sLabel}>Průběh</div>
                <div style={S.barWrap}>
                  <div style={{ ...S.barFill, width: `${progress}%` }} />
                </div>
                <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-secondary)' }}>
                  {progMsg}
                </div>
              </div>
            )}

            <button
              style={{ ...S.dlBtn, ...(!bbox || downloading ? S.dlBtnDisabled : {}) }}
              onClick={handleDownload}
              disabled={!bbox || downloading}
            >
              {downloading ? 'Stahuji...' : '↓ Stáhnout'}
            </button>
          </div>
        </div>

        <div style={S.footer}>{statusMsg}</div>
      </div>
    </div>
  );
}
