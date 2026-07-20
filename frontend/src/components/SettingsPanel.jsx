import React, { useRef, useState } from 'react';

const S = {
  panel: {
    width: 350,
    flexShrink: 0,
    background: 'var(--panel-bg)',
    borderRight: '0.5px solid var(--panel-border)',
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
  },
  section: {
    padding: '14px 16px',
    borderBottom: '0.5px solid var(--panel-border)',
  },
  label: {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    fontWeight: 500,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--text-secondary)',
    marginBottom: 10,
  },
  dropZone: {
    border: '1px dashed var(--panel-border)',
    borderRadius: 'var(--radius-md)',
    padding: '14px 12px',
    textAlign: 'center',
    cursor: 'pointer',
    background: '#fafaf8',
    transition: 'border-color 0.15s',
    marginBottom: 6,
  },
  dropIcon: { fontSize: 20, color: 'var(--text-muted)', marginBottom: 5 },
  dropText: { fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 },
  dropExt: {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    color: 'var(--text-muted)',
    marginTop: 3,
  },
  fileLoaded: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 10px',
    borderRadius: 'var(--radius-md)',
    background: '#f6f9f3',
    border: '0.5px solid #d0e0c0',
    marginBottom: 6,
  },
  fileLoadedDsm: {
    background: '#f3f8fb',
    border: '0.5px solid #b8d4e4',
  },
  fileName: {
    flex: 1,
    fontFamily: 'var(--mono)',
    fontSize: 11,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  fileSize: { fontSize: 10, color: 'var(--text-muted)', flexShrink: 0 },
  removeBtn: {
    background: 'none',
    border: 'none',
    color: 'var(--text-muted)',
    cursor: 'pointer',
    fontSize: 14,
    lineHeight: 1,
    padding: '0 2px',
    flexShrink: 0,
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  settingLabel: { fontSize: 12, color: 'var(--text-secondary)' },
  select: {
    fontFamily: 'var(--mono)',
    fontSize: 11,
    padding: '3px 6px',
    borderRadius: 'var(--radius-sm)',
    border: '0.5px solid var(--panel-border)',
    background: '#fafaf8',
    color: 'var(--text-primary)',
    cursor: 'pointer',
  },
  numInput: {
    fontFamily: 'var(--mono)',
    fontSize: 11,
    padding: '3px 6px',
    borderRadius: 'var(--radius-sm)',
    border: '0.5px solid var(--panel-border)',
    background: '#fafaf8',
    width: 64,
    textAlign: 'right',
    color: 'var(--text-primary)',
  },
  layerRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '5px 0',
    cursor: 'pointer',
  },
  layerDot: {
    width: 10,
    height: 10,
    borderRadius: 2,
    flexShrink: 0,
  },
  layerName: { fontSize: 12, flex: 1 },
  toggle: {
    width: 30,
    height: 17,
    borderRadius: 9,
    border: 'none',
    cursor: 'pointer',
    position: 'relative',
    flexShrink: 0,
    transition: 'background 0.2s',
  },
  toggleKnob: {
    position: 'absolute',
    width: 11,
    height: 11,
    borderRadius: '50%',
    background: '#fff',
    top: 3,
    transition: 'left 0.2s',
  },
  optionalListbox: {
    border: '0.5px solid var(--panel-border)',
    borderRadius: 'var(--radius-md)',
    minHeight: 52,
    padding: 6,
    marginBottom: 6,
    background: '#fafaf8',
  },
  optionalItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '3px 4px',
    borderRadius: 4,
  },
  optionalItemName: {
    flex: 1,
    fontFamily: 'var(--mono)',
    fontSize: 10,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    color: 'var(--text-secondary)',
  },
  addBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    width: '100%',
    padding: '6px 0',
    borderRadius: 'var(--radius-sm)',
    border: '0.5px solid var(--panel-border)',
    background: 'none',
    fontSize: 11,
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    fontFamily: 'var(--mono)',
    marginBottom: 4,
    transition: 'background 0.15s',
  },
};

const TOOLTIPS = {
  crs: 'Souřadnicový systém výstupu. pokud chcete magnetické poledníky, nastavte mag. deklinaci vůči tomuto CRS',
  lidar: 'Nahrajte data ze zařízení nebo vyberte oblast tažením v mapě a stáhněte.',
  scale: 'Měřítko výsledné mapy. 1:10 000 pro detailní mapy, 1:15 000 pro větší oblasti.',
  paper: 'Formát výstupního PNG. Pokud je vybrán "Extent dat" mapa se ořízne přesně na rozsah dat.',
  contourInterval: 'Základní interval vrstevnic v metrech. Hlavní vrstevnice se kreslí po 5násobku tohoto intervalu, pomocné po jeho polovině. Výchozí 5 m.',
  sigma: 'Míra vyhlazení vrstevnic. Vyšší hodnota = hladší vrstevnice, ale méně detailní. Doporučeno 3–6.',
  slopeThreshold: 'Minimální sklon terénu (ve stupních) aby byl prvek klasifikován jako skála. Nižší = více skal, ale budou více splývat.',
  northRotation: 'Odchylka mag. severu od zvoleného souřadnicového systému.',
  bin1: 'Výška do které je vegetace považována za otevřený prostor (znaky 401 a 403).',
  bin2: 'Výška do které je vegetace klasifikována jako znak (znak 410).',
  bin3: 'Výška do které je vegetace klasifikována jako chůze (znak 408).',
  bin4: 'Výška do které je vegetace klasifikována jako znak 406. Nad touto výškou = les (znak 405).',
  zabaged: 'Vyberte celou sadu shapefile souborů (.shp, .dbf, .shx, .prj). V seznamu se zobrazí jen .shp soubory. Název musí odpovídat vrstvě ZABAGED® (např. "VodniTok.shp")',
  other: 'Jakákoliv jiná vrstva ve formátu .shp, která svýmnázvem odpovídá danému znaku (např. "301.shp")'
};

// Tooltip komponent
function Tooltip({ text }) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const btnRef = useRef();

  const show = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    setPos({ x: r.right + 8, y: r.top });
    setVisible(true);
  };
  const hide = () => setVisible(false);

  return (
    <>
      <button
        ref={btnRef}
        onMouseEnter={show}
        onMouseLeave={hide}
        style={{
          background: 'none', border: 'none', cursor: 'help',
          color: 'var(--text-muted)', fontSize: 11, lineHeight: 1,
          padding: '0 3px', flexShrink: 0, borderRadius: '50%',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 15, height: 15,
          border: '0.5px solid var(--panel-border)',
        }}
        tabIndex={-1}
      >?</button>
      {visible && (
        <div style={{
          position: 'fixed',
          left: pos.x,
          top: pos.y,
          zIndex: 9999,
          background: 'var(--ink)',
          color: '#fff',
          fontSize: 11,
          fontFamily: 'var(--sans)',
          lineHeight: 1.5,
          padding: '7px 10px',
          borderRadius: 6,
          maxWidth: 220,
          boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
          pointerEvents: 'none',
        }}>
          {text}
        </div>
      )}
    </>
  );
}

function CollapsibleSection({ label, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ borderBottom: '0.5px solid var(--panel-border)' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          width: '100%', padding: '12px 16px', background: 'none', border: 'none',
          cursor: 'pointer', textAlign: 'left',
        }}
        onMouseEnter={(e) => e.currentTarget.style.background = '#f5f4f0'}
        onMouseLeave={(e) => e.currentTarget.style.background = 'none'}
      >
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 10, fontWeight: 500,
          letterSpacing: '0.08em', textTransform: 'uppercase',
          color: 'var(--text-secondary)',
        }}>{label}</span>
        <span style={{
          fontSize: 10, color: 'var(--text-muted)',
          transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
          transition: 'transform 0.2s', display: 'inline-block',
        }}>▼</span>
      </button>
      {open && (
        <div style={{ padding: '0 16px 14px' }}>
          {children}
        </div>
      )}
    </div>
  );
}

const CRS_OPTIONS = [
  { label: 'S-JTSK (ČR) EPSG:5514', value: 'EPSG:5514' },
  { label: 'UTM 33N EPSG:32633', value: 'EPSG:32633' },
  { label: 'UTM 32N EPSG:32632', value: 'EPSG:32632' },
  { label: 'UTM 34N EPSG:32634', value: 'EPSG:32634' },
  { label: 'S-JTSK/03 EPSG:2065', value: 'EPSG:2065' },
];

const PAPER_OPTIONS = ['A4 na šířku', 'A4 na výšku', 'A3 na šířku', 'A3 na výšku', 'Extent dat'];

const LAYERS = [
  { key: 'contours', label: 'Vrstevnice a terén', color: '#c96a3a' },
  { key: 'rocks', label: 'Skály a balvany', color: '#888' },
  { key: 'water', label: 'Voda a bažiny', color: '#317fa0' },
  { key: 'vegetation', label: 'Vegetace', color: '#6b9950' },
  { key: 'roads', label: 'Cesty a silnice', color: '#f0b643' },
  { key: 'buildings', label: 'Budovy', color: '#2c2c2c' },
  { key: 'man_made', label: 'Umělé prvky', color: '#8060b0' },
  { key: 'magnetic_lines', label: 'Magnetické poledníky', color: '#7bc7e6' },
];

function FileDropZone({ id, label, icon, accept, file, onFile, onRemove, colorStyle }) {
  const ref = useRef();
  const handleDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) onFile(f);
  };
  const handleChange = (e) => {
    const f = e.target.files[0];
    if (f) onFile(f);
  };
  const formatSize = (b) => b > 1e6 ? (b / 1e6).toFixed(1) + ' MB' : (b / 1e3).toFixed(0) + ' KB';

  if (file) {
    return (
      <div style={{ ...S.fileLoaded, ...(colorStyle || {}) }}>
        <span style={{ fontSize: 15, color: colorStyle ? 'var(--water)' : 'var(--forest)' }}>◈</span>
        <span style={S.fileName}>{file.name}</span>
        <span style={S.fileSize}>{formatSize(file.size)}</span>
        <button style={S.removeBtn} onClick={onRemove} title="Odebrat soubor">×</button>
      </div>
    );
  }

  return (
    <div
      style={S.dropZone}
      onClick={() => ref.current.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
      onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--rock)'}
      onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--panel-border)'}
    >
      <div style={S.dropIcon}>{icon}</div>
      <p style={S.dropText}>{label}</p>
      <div style={S.dropExt}>{accept}</div>
      <input ref={ref} type="file" accept={accept} style={{ display: 'none' }} onChange={handleChange} />
    </div>
  );
}

function Toggle({ on, onChange }) {
  return (
    <button
      style={{ ...S.toggle, background: on ? 'var(--forest-mid)' : 'var(--panel-border)' }}
      onClick={onChange}
      aria-checked={on}
      role="switch"
    >
      <div style={{ ...S.toggleKnob, left: on ? 16 : 3 }} />
    </button>
  );
}

export default function SettingsPanel({ settings, onSettings, files, onFiles, isMobile }) {
  const zabRef = useRef();
  const isomRef = useRef();

  const set = (key, val) => onSettings({ ...settings, [key]: val });
  const toggleLayer = (key) =>
    onSettings({ ...settings, layers: { ...settings.layers, [key]: !settings.layers[key] } });

  const addFiles = (type, newFiles) => {
    const existing = files[type] || [];
    const existingNames = new Set(existing.map(f => f.name));
    const toAdd = Array.from(newFiles).filter(f => !existingNames.has(f.name));
    onFiles({ ...files, [type]: [...existing, ...toAdd] });
  };
  const removeOptional = (type, idx) => {
    const arr = [...files[type]];
    arr.splice(idx, 1);
    onFiles({ ...files, [type]: arr });
  };

  return (
    <div style={{
      ...S.panel,
      width: isMobile ? '100%' : 'clamp(260px, 22vw, 380px)',
      ...(isMobile && { fontSize: 13 }),
    }}>
      {/* LiDAR */}
      <div style={{ ...S.section, padding: isMobile ? '16px' : '14px 16px' }}>
        <div style={S.label}>LiDAR data</div>
        <FileDropZone
          label="Přetáhni nebo klikni pro DMR"
          icon="⛰️"
          accept=".las,.laz"
          file={files.dtm}
          onFile={(f) => onFiles({ ...files, dtm: f })}
          onRemove={() => onFiles({ ...files, dtm: null })}
        />
        <FileDropZone
          label="Přetáhni nebo klikni pro DMP"
          icon="🌲"
          accept=".las,.laz,"
          file={files.dsm}
          onFile={(f) => onFiles({ ...files, dsm: f })}
          onRemove={() => onFiles({ ...files, dsm: null })}
          colorStyle={S.fileLoadedDsm}
        />
      </div>

      {/* Mapa */}
      <div style={S.section}>
        <div style={S.label}>Nastavení mapy</div>
        <div style={S.row}>
          <span style={S.settingLabel}>Souřadnicový systém</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Tooltip text={TOOLTIPS.crs} />
            <select style={S.select} value={settings.crs} onChange={(e) => set('crs', e.target.value)}>
              {CRS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>
        <div style={S.row}>
          <span style={S.settingLabel}>Měřítko</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Tooltip text={TOOLTIPS.scale} />
            <select style={S.select} value={settings.scale} onChange={(e) => set('scale', e.target.value)}>
              <option value="10000">1 : 10 000</option>
              <option value="15000">1 : 15 000</option>
            </select>
          </div>
        </div>
        <div style={S.row}>
          <span style={S.settingLabel}>Formát papíru</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Tooltip text={TOOLTIPS.paper} />
            <select style={S.select} value={settings.paper} onChange={(e) => set('paper', e.target.value)}>
              {PAPER_OPTIONS.map((o) => <option key={o}>{o}</option>)}
            </select>
          </div>
        </div>
        <div style={S.row}>
          <span style={S.settingLabel}>Interval vrstevnic (m)</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Tooltip text={TOOLTIPS.contourInterval} />
            <input style={S.numInput} type="number" step="0.5" min="0.5" max="50"
              value={settings.contourInterval} onChange={(e) => set('contourInterval', e.target.value)} />
          </div>
        </div>
        <div style={S.row}>
          <span style={S.settingLabel}>Vyhlazení vrstevnic</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Tooltip text={TOOLTIPS.sigma} />
            <input style={S.numInput} type="number" step="0.5" min="0" max="20"
              value={settings.sigma} onChange={(e) => set('sigma', e.target.value)} />
          </div>
        </div>
        <div style={S.row}>
          <span style={S.settingLabel}>Minimální sklon skal (°)</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Tooltip text={TOOLTIPS.slopeThreshold} />
            <input style={S.numInput} type="number" step="1" min="20" max="80"
              value={settings.slopeThreshold} onChange={(e) => set('slopeThreshold', e.target.value)} />
          </div>
        </div>
        <div style={S.row}>
          <span style={S.settingLabel}>Mag. deklinace (°)</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Tooltip text={TOOLTIPS.northRotation} />
            <input style={S.numInput} type="number" step="0.1"
              value={settings.northRotation} onChange={(e) => set('northRotation', e.target.value)} />
          </div>
        </div>
      </div>

      {/* Vegetace */}
      <CollapsibleSection label="Vegetace" defaultOpen={false}>
        <div style={S.section}>
          <div style={S.label}>Výška vegetace (m)</div>
          {[
            ['Otevřený prostor (do)', 'bin1'],
            ['Boj (do)', 'bin2'],
            ['Chůze (do)', 'bin3'],
            ['Pomalý běh (do)', 'bin4'],
          ].map(([lbl, key]) => (
            <div style={S.row} key={key}>
              <span style={S.settingLabel}>{lbl}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Tooltip text={TOOLTIPS[key]} />
                <input style={S.numInput} type="number" step="0.5" min="0" max="30"
                  value={settings[key]} onChange={(e) => set(key, e.target.value)} />
              </div>
            </div>
          ))}
        </div>
      </CollapsibleSection>
      {/* Mikrotvary — rozbalovací */}
      <CollapsibleSection label="Tvary reliéfu" defaultOpen={false}>
        <div style={{ ...S.label, marginBottom: 8 }}>Prohlubně</div>
        {[
          ['Min. průměr (m)', 'depMinDiameter', '0.5', '0.5', '50', 'Minimální průměr prohlubně v metrech. Menší objekty se ignorují.'],
          ['Max. průměr (m)', 'depMaxDiameter', '0.5', '0.5', '50', 'Maximální průměr prohlubně. Větší objekty se ignorují.'],
          ['Min. hloubka (m)', 'depMinDepth', '0.1', '0.1', '10', 'Minimální hloubka prohlubně v metrech.'],
        ].map(([lbl, key, step, min, max, tip]) => (
          <div style={S.row} key={key}>
            <span style={S.settingLabel}>{lbl}</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Tooltip text={tip} />
              <input style={S.numInput} type="number" step={step} min={min} max={max}
                value={settings[key]} onChange={(e) => set(key, e.target.value)} />
            </div>
          </div>
        ))}

        <div style={{ ...S.label, marginTop: 12, marginBottom: 8 }}>Kupky</div>
        {[
          ['Min. průměr (m)', 'knoMinDiameter', '0.5', '0.5', '50', 'Minimální průměr kupky v metrech.'],
          ['Max. průměr (m)', 'knoMaxDiameter', '0.5', '0.5', '50', 'Maximální průměr kupky. Větší kopce se ignorují.'],
          ['Min. výška (m)', 'knoMinHeight', '0.1', '0.1', '10', 'Minimální výška kupky nad okolním terénem.'],
        ].map(([lbl, key, step, min, max, tip]) => (
          <div style={S.row} key={key}>
            <span style={S.settingLabel}>{lbl}</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Tooltip text={tip} />
              <input style={S.numInput} type="number" step={step} min={min} max={max}
                value={settings[key]} onChange={(e) => set(key, e.target.value)} />
            </div>
          </div>
        ))}
      </CollapsibleSection>

      {/* Vrstvy */}
      <div style={S.section}>
        <div style={S.label}>Vrstvy</div>
        {LAYERS.map((l) => (
          <div style={S.layerRow} key={l.key} onClick={() => toggleLayer(l.key)}>
            <div style={{ ...S.layerDot, background: l.color }} />
            <span style={S.layerName}>{l.label}</span>
            <Toggle on={settings.layers[l.key]} onChange={() => toggleLayer(l.key)} />
          </div>
        ))}
      </div>

      {/* Volitelná data */}
      <div style={{ ...S.section, flex: 1 }}>
        <div style={S.label}>Volitelná vektorová data</div>

        {/* Checkbox: automatické stažení ZABAGED přes WFS */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <input
            type="checkbox"
            id="downloadZabaged"
            checked={!!settings.download_zabaged}
            onChange={(e) => set('download_zabaged', e.target.checked)}
            style={{ cursor: 'pointer', width: 14, height: 14 }}
          />
          <label htmlFor="downloadZabaged" style={{ fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer', userSelect: 'none' }}>
            Stáhnout ZABAGED® automaticky z ČÚZK
          </label>
          <Tooltip text="Automaticky stáhne vektorová data ZABAGED® pro oblast přes WFS službu ČÚZK." />
        </div>
        {/*
        {!settings.download_zabaged && (
        <>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>
          ZABAGED® (.shp) 
          <Tooltip text={TOOLTIPS.zabaged} />
        </div>
        <div style={S.optionalListbox}>
          {(files.zabaged || []).filter(f => f.name.toLowerCase().endsWith('.shp')).map((f) => {
            const baseName = f.name.replace(/\.shp$/i, '');
            return (
              <div style={S.optionalItem} key={f.name}>
                <span style={S.optionalItemName}>{f.name}</span>
                <button style={S.removeBtn} onClick={() => {
                  onFiles({
                    ...files,
                    zabaged: (files.zabaged || []).filter(
                      x => x.name.replace(/\.[^.]+$/, '') !== baseName
                    ),
                  });
                }}>×</button>
              </div>
            );
          })}
          {!(files.zabaged || []).some(f => f.name.toLowerCase().endsWith('.shp')) && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: '4px 4px' }}>
              Žádné soubory
            </div>
          )}
        </div>
        <button style={S.addBtn}
          onClick={() => zabRef.current.click()}
          onMouseEnter={(e) => e.currentTarget.style.background = '#f5f4f0'}
          onMouseLeave={(e) => e.currentTarget.style.background = 'none'}
        >
          + Přidat ZABAGED® soubory
        </button>
        <input ref={zabRef} type="file" accept=".shp,.dbf,.shx,.prj,.cpg,.qpj" multiple style={{ display: 'none' }}
          onChange={(e) => addFiles('zabaged', e.target.files)} />
        </>
        )}

        <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6, marginTop: 8 }}>
          Vlastní vrstvy (.shp) 
          <Tooltip text={TOOLTIPS.other} />
        </div>
        <div style={S.optionalListbox}>
          {(files.isom || []).filter(f => f.name.toLowerCase().endsWith('.shp')).map((f) => {
            const baseName = f.name.replace(/\.shp$/i, '');
            return (
              <div style={S.optionalItem} key={f.name}>
                <span style={S.optionalItemName}>{f.name}</span>
                <button style={S.removeBtn} onClick={() => {
                  onFiles({
                    ...files,
                    isom: (files.isom || []).filter(
                      x => x.name.replace(/\.[^.]+$/, '') !== baseName
                    ),
                  });
                }}>×</button>
              </div>
            );
          })}
          {!(files.isom || []).some(f => f.name.toLowerCase().endsWith('.shp')) && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: '4px 4px' }}>
              Žádné soubory
            </div>
          )}
        </div>
        <button style={S.addBtn}
          onClick={() => isomRef.current.click()}
          onMouseEnter={(e) => e.currentTarget.style.background = '#f5f4f0'}
          onMouseLeave={(e) => e.currentTarget.style.background = 'none'}
        >
          + Přidat ISOM vrstvy
        </button>
        <input ref={isomRef} type="file" accept=".shp,.dbf,.shx,.prj,.cpg,.qpj" multiple style={{ display: 'none' }}
          onChange={(e) => addFiles('isom', e.target.files)} /> 
          */}
      </div>
    </div>
  );
}

export const DEFAULT_SETTINGS = {
  crs: 'EPSG:5514',
  scale: '10000',
  paper: 'A4 na šířku',
  contourInterval: 5,
  sigma: 4,
  slopeThreshold: 45,
  northRotation: 5.0,
  bin1: 1, bin2: 2, bin3: 6, bin4: 12,
  depMinDiameter: 2, depMaxDiameter: 5, depMinDepth: 0.7,
  knoMinDiameter: 1.5, knoMaxDiameter: 10, knoMinHeight: 0.5,
  download_zabaged: false,
  layers: {
    contours: true, rocks: true, water: true,
    vegetation: true, roads: true, buildings: true,
    man_made: true, magnetic_lines: false,
  },
};