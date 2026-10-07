import React, { useEffect, useState } from 'react';
import MapCanvas from './MapCanvas';
import LayerSelector from './LayerSelector';
import { useVectorElements, MAP_PAPER } from './VectorPreview';

const S = {
  overlay: {
    position: 'fixed', inset: 0, zIndex: 2000,
    background: 'rgba(15,42,54,0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  modal: {
    background: 'var(--panel-bg)', color: 'var(--text-primary)',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
    boxShadow: '0 12px 48px rgba(0,0,0,0.3)',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
    borderBottom: '3px solid transparent', borderImage: 'var(--brand-gradient) 1',
    flexShrink: 0,
  },
  title: { fontFamily: 'var(--heading)', fontWeight: 700, fontSize: 15, flex: 1, minWidth: 0 },
  seg: {
    display: 'flex', border: '0.5px solid var(--panel-border)',
    borderRadius: 'var(--radius-sm)', overflow: 'hidden', flexShrink: 0,
  },
  segBtn: {
    padding: '5px 12px', fontSize: 11, fontFamily: 'var(--mono)', border: 'none',
    background: 'none', color: 'var(--text-secondary)', cursor: 'pointer',
  },
  segBtnActive: { background: 'var(--accent-soft)', color: 'var(--accent-strong)' },
  close: {
    background: 'none', border: 'none', color: 'var(--text-secondary)',
    fontSize: 24, lineHeight: 1, cursor: 'pointer', padding: '0 4px', flexShrink: 0,
  },
  body: { flex: 1, display: 'flex', minHeight: 0 },
  mapArea: { flex: 1, minWidth: 0, minHeight: 0, position: 'relative' },
  side: {
    background: 'var(--panel-bg)', overflowY: 'auto', flexShrink: 0,
    display: 'flex', flexDirection: 'column',
  },
  section: { padding: '12px 14px', borderBottom: '0.5px solid var(--panel-border)' },
  label: {
    fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em',
    textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8,
  },
  hint: { fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--mono)', lineHeight: 1.5, marginTop: 8 },
  btn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
    width: '100%', padding: '8px 0', marginBottom: 6, borderRadius: 'var(--radius-md)',
    fontSize: 12, fontFamily: 'var(--sans)', textDecoration: 'none', cursor: 'pointer',
    border: '0.5px solid var(--panel-border)', background: 'none', color: 'var(--text-primary)',
  },
  btnPrimary: { background: 'var(--brand-gradient)', color: '#fff', border: 'none', fontWeight: 600 },
  center: {
    position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: '#777', fontFamily: 'var(--mono)', fontSize: 12, background: MAP_PAPER,
  },
};

// Načte rozměry PNG, aby šel vložit do SVG plátna jako <image>
function useImageSize(url) {
  const [size, setSize] = useState(null);
  useEffect(() => {
    if (!url) { setSize(null); return undefined; }
    let alive = true;
    setSize(null);
    const img = new Image();
    img.onload = () => alive && setSize({ w: img.naturalWidth, h: img.naturalHeight });
    img.onerror = () => alive && setSize({ error: true });
    img.src = url;
    return () => { alive = false; };
  }, [url]);
  return size;
}

export default function ResultViewer({
  onClose, isMobile, vectorData, vectorsLoading, symbolColors,
  selectedCodes, onSelectedChange, pngUrl, gpkgUrl, onRenderCustom, exporting,
}) {
  const [mode, setMode] = useState(vectorData ? 'vectors' : 'png');
  const hasFilter = selectedCodes !== null;
  const { elements, width, height } = useVectorElements(vectorData, selectedCodes, symbolColors);
  const imgSize = useImageSize(mode === 'png' ? pngUrl : null);

  // Jakmile dorazí vektory, přepni na ně (okno se otevírá hned po dokončení jobu)
  useEffect(() => { if (vectorData) setMode('vectors'); }, [vectorData]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleRender = async () => {
    await onRenderCustom();
    setMode('png');
  };

  const modalStyle = isMobile
    ? { ...S.modal, width: '100vw', height: '100%' }
    : { ...S.modal, width: 'min(1500px, 96vw)', height: '92vh', borderRadius: 'var(--radius-lg)' };
  const bodyStyle = isMobile ? { ...S.body, flexDirection: 'column' } : S.body;
  const sideStyle = isMobile
    ? { ...S.side, maxHeight: '42%', borderTop: '0.5px solid var(--panel-border)' }
    : { ...S.side, width: 300, borderLeft: '0.5px solid var(--panel-border)' };

  let mapContent;
  if (mode === 'vectors') {
    mapContent = elements ? (
      <MapCanvas contentWidth={width} contentHeight={height} background={MAP_PAPER} resetKey="vectors">
        {elements}
      </MapCanvas>
    ) : (
      <div style={S.center}>{vectorsLoading ? 'Načítám vektorová data…' : 'Vektorová data nejsou k dispozici'}</div>
    );
  } else if (!imgSize) {
    mapContent = <div style={S.center}>Načítám PNG…</div>;
  } else if (imgSize.error) {
    mapContent = <div style={S.center}>PNG se nepodařilo načíst</div>;
  } else {
    mapContent = (
      <MapCanvas contentWidth={imgSize.w} contentHeight={imgSize.h} background="#e9ecec" resetKey={pngUrl}>
        <image href={pngUrl} x={0} y={0} width={imgSize.w} height={imgSize.h} />
      </MapCanvas>
    );
  }

  return (
    <div style={S.overlay} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Výsledná mapa">
        <div style={S.header}>
          <div style={S.title}>Výsledná mapa</div>
          <div style={S.seg}>
            <button
              style={{ ...S.segBtn, ...(mode === 'vectors' ? S.segBtnActive : {}) }}
              onClick={() => setMode('vectors')}
              disabled={!vectorData}
              title="Vektorový náhled — vrstvy jde zapínat a vypínat"
            >Vektor</button>
            <button
              style={{ ...S.segBtn, ...(mode === 'png' ? S.segBtnActive : {}) }}
              onClick={() => setMode('png')}
              title="PNG s plnou ISOM psecifikací"
            >PNG</button>
          </div>
          <button style={S.close} onClick={onClose} title="Zavřít (Esc)">×</button>
        </div>

        <div style={bodyStyle}>
          <div style={S.mapArea}>{mapContent}</div>

          <div style={sideStyle}>
            {vectorData && (
              <div style={S.section}>
                <div style={S.label}>Vrstvy</div>
                <LayerSelector
                  vectorData={vectorData}
                  selectedCodes={selectedCodes}
                  onChange={onSelectedChange}
                  symbolColors={symbolColors}
                  showBulk
                />
                <div style={S.hint}>
                  {mode === 'png'
                    ? 'PNG ukazuje vyrenderovaný stav. Změny vrstev se do něj promítnou po „Vyrenderovat PNG“.'
                    : 'Vektorový náhled je zjednodušený — plný znakový klíč je v PNG.'}
                </div>
              </div>
            )}

            <div style={S.section}>
              <div style={S.label}>Export</div>
              {hasFilter && (
                <button style={{ ...S.btn, ...S.btnPrimary, opacity: exporting ? 0.6 : 1 }}
                  onClick={handleRender} disabled={exporting}>
                  {exporting ? '⏳ Renderuji výběr…' : '⚙ Vyrenderovat PNG s vybranými vrstvami'}
                </button>
              )}
              <a style={{ ...S.btn, ...(hasFilter ? {} : S.btnPrimary) }} href={pngUrl} download="OMap.png">
                ↓ Stáhnout PNG
              </a>
              <a style={S.btn} href={gpkgUrl} download="OMap.gpkg">
                ↓ Exportovat GPKG pro OOM
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
