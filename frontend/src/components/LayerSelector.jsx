import React, { useMemo, useState } from 'react';
import { symbolColor } from './VectorPreview';

const GROUP_LABELS = {
  contours: 'Terén / vrstevnice',
  rocks: 'Skály',
  water: 'Voda',
  vegetation: 'Vegetace',
  roads: 'Komunikace',
  man_made: 'Umělé objekty',
  buildings: 'Budovy',
  private: 'Privátní oblasti',
  other: 'Vlastní ISOM vrstvy',
};

const S = {
  wrap: { fontFamily: 'var(--mono)', fontSize: 11 },
  groupRow: {
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '4px 0', cursor: 'pointer', userSelect: 'none',
  },
  groupLabel: { flex: 1, fontWeight: 500, cursor: 'pointer' },
  caret: { fontSize: 9, color: 'var(--text-muted)', width: 10 },
  codeRow: {
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '2px 0 2px 20px', fontSize: 10, color: 'var(--text-secondary)', cursor: 'pointer',
  },
  swatch: {
    width: 10, height: 10, borderRadius: 2, flexShrink: 0,
    boxShadow: '0 0 0 1px var(--panel-border)',
  },
  bulkRow: { display: 'flex', gap: 6, marginBottom: 8 },
  bulkBtn: {
    flex: 1, padding: '4px 0', fontSize: 10, fontFamily: 'var(--mono)',
    border: '0.5px solid var(--panel-border)', borderRadius: 'var(--radius-sm)',
    background: 'none', color: 'var(--text-secondary)', cursor: 'pointer',
  },
};

/**
 * vectorData: GeoJSON FeatureCollection s properties {code, sym_key, group} na každém feature
 * selectedCodes: Set<string> | null (null = všechny vybrané)
 * onChange: (newSelectedCodes: Set<string> | null) => void
 * symbolColors: {kód: barva} — volitelné, zobrazí barevné vzorky
 * showBulk: tlačítka Zapnout vše / Vypnout vše
 */
export default function LayerSelector({ vectorData, selectedCodes, onChange, symbolColors, showBulk }) {
  const [openGroups, setOpenGroups] = useState({});

  const { groups, allCodes } = useMemo(() => {
    const g = {};
    const all = new Set();
    (vectorData?.features || []).forEach((f) => {
      const { code, sym_key, group } = f.properties || {};
      if (!code) return;
      all.add(code);
      if (!g[group]) g[group] = {};
      if (!g[group][code]) g[group][code] = new Set();
      g[group][code].add(sym_key);
    });
    return { groups: g, allCodes: all };
  }, [vectorData]);

  const isSelected = (code) => selectedCodes === null || selectedCodes.has(code);

  const setCodes = (mutator) => {
    const base = selectedCodes === null ? new Set(allCodes) : new Set(selectedCodes);
    mutator(base);
    // pokud je vybráno úplně vše → reprezentuj jako null (= "bez filtru")
    onChange(base.size === allCodes.size ? null : base);
  };

  const toggleCode = (code) => {
    setCodes((base) => {
      if (base.has(code)) base.delete(code); else base.add(code);
    });
  };

  const toggleGroup = (groupName, codes) => {
    const allOn = codes.every((c) => isSelected(c));
    setCodes((base) => {
      codes.forEach((c) => { if (allOn) base.delete(c); else base.add(c); });
    });
  };

  if (!vectorData) return null;

  return (
    <div style={S.wrap}>
      {showBulk && (
        <div style={S.bulkRow}>
          <button style={S.bulkBtn} onClick={() => onChange(null)}>Zapnout vše</button>
          <button style={S.bulkBtn} onClick={() => onChange(new Set())}>Vypnout vše</button>
        </div>
      )}
      {Object.entries(groups).map(([groupName, codeMap]) => {
        const codes = Object.keys(codeMap).sort((a, b) => parseFloat(a) - parseFloat(b));
        const allOn = codes.every((c) => isSelected(c));
        const someOn = codes.some((c) => isSelected(c));
        const open = !!openGroups[groupName];
        return (
          <div key={groupName}>
            <div style={S.groupRow}>
              <span style={S.caret} onClick={() => setOpenGroups((o) => ({ ...o, [groupName]: !open }))}>
                {open ? '▾' : '▸'}
              </span>
              <input
                type="checkbox"
                checked={allOn}
                ref={(el) => { if (el) el.indeterminate = !allOn && someOn; }}
                onChange={() => toggleGroup(groupName, codes)}
              />
              {symbolColors && <span style={{ ...S.swatch, background: symbolColor(codes[0], groupName, symbolColors) }} />}
              <span style={S.groupLabel} onClick={() => setOpenGroups((o) => ({ ...o, [groupName]: !open }))}>
                {GROUP_LABELS[groupName] || groupName}
              </span>
              <span style={{ color: 'var(--text-muted)' }}>{codes.length}</span>
            </div>
            {open && codes.map((code) => (
              <label style={S.codeRow} key={code}>
                <input type="checkbox" checked={isSelected(code)} onChange={() => toggleCode(code)} />
                {symbolColors && <span style={{ ...S.swatch, background: symbolColor(code, groupName, symbolColors) }} />}
                <span>ISOM {code}</span>
              </label>
            ))}
          </div>
        );
      })}
    </div>
  );
}
