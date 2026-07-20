import React, { useState } from 'react';

const STEPS = [
  {
    icon: '↓',
    title: 'Stáhněte data',
    desc: 'V mapovém okně vyberte oblast nástrojem "Výběr oblasti" —> táhněte myší. Nad mapou se zobrazí panel pro stažení DMR a DMP dat. Vyberte zdroj dat pro vybranou zemi a klikněte na "Stáhnout". Stahování trvá několik desítek sekund pro ČR pro jiné země může být doba stahování delší. Když se data stáhnou, automaticky se vloží jako vstupní',
  },
  {
    icon: '📁',
    title: 'Nebo nahrajte vlastní soubory',
    desc: 'Máte-li vlastní LiDAR data, přetáhněte je do levého panelu.Oba modely, DMR (digitální model reliéfu) a DMP (digitální model povrchu), musí být ve formátu .las, .laz. Aplikace nerozezná data DMR a DMP v jednom souboru.',
  },
  {
    icon: '⚙',
    title: 'Nastavte parametry mapy',
    desc: 'V levém panelu nastavte souřadnicový systém výstupu, měřítko (1:10 000 nebo 1:15 000), formát papíru (pokud chcete výstu primárně v PNG) a parametry zpracování. U každého parametru najdete nápovědu po najetí na ikonu "?"',
  },
  {
    icon: '▶',
    title: 'Generujte mapu',
    desc: 'Klikněte na "Generovat mapu" v pravé liště. Zpracování trvá obvykle 2–10 minut podle velikosti oblasti. Průběh sledujte v pravém panelu.',
  },
  {
    icon: '🌲',
    title: 'Volitelná ZABAGED® data',
    desc: ('Zakliknutím checkboxu je možné vykreslit také data ze ZABAGED®, zatím pouze bez možnosti výběru jednotlivých vrstev.')
  },
  {
    icon: '🗺',
    title: 'Stáhněte výsledky',
    desc: 'Po dokončení si stáhněte PNG mapu (500 DPI) nebo GPKG soubor, který je možné importovat do OpenOrienteering Mapperu pomocí CRT souboru, který stáhnete také v pravé liště',
  },
    ];
        
const S = {
  overlay: {
    position: 'fixed', inset: 0,
    background: 'rgba(26,31,46,0.6)',
    zIndex: 9999,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  modal: {
    background: '#fff',
    borderRadius: 12,
    width: 580,
    maxWidth: '95vw',
    maxHeight: '90vh',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    boxShadow: '0 12px 48px rgba(0,0,0,0.2)',
  },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '18px 24px 14px',
    borderBottom: '0.5px solid #e2ddd3',
    background: '#1a1f2e',
    color: '#fff',
  },
  headerLeft: { display: 'flex', alignItems: 'center', gap: 10 },
  dot: { width: 8, height: 8, borderRadius: '50%', background: '#c96a3a', flexShrink: 0 },
  title: { fontFamily: 'IBM Plex Mono, monospace', fontSize: 14, fontWeight: 500, letterSpacing: '0.04em' },
  subtitle: { fontSize: 11, opacity: 0.5, fontFamily: 'IBM Plex Mono, monospace', marginTop: 2 },
  closeBtn: {
    background: 'none', border: 'none', color: '#fff',
    fontSize: 20, cursor: 'pointer', opacity: 0.6, lineHeight: 1,
    padding: '2px 6px',
  },
  body: { overflowY: 'auto', padding: '20px 24px 24px' },
  stepsGrid: {
    display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14,
  },
  step: {
    display: 'flex', gap: 12, padding: '14px',
    borderRadius: 8, background: '#fafaf8',
    border: '0.5px solid #e2ddd3',
  },
  stepIcon: {
    fontSize: 22, flexShrink: 0, width: 36, height: 36,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: '#f0ead6', borderRadius: 8,
  },
  stepNum: {
    fontFamily: 'IBM Plex Mono, monospace', fontSize: 9,
    color: '#c96a3a', fontWeight: 500, letterSpacing: '0.06em',
    marginBottom: 3,
  },
  stepTitle: { fontSize: 12, fontWeight: 500, marginBottom: 5, color: '#1a1f2e' },
  stepDesc: { fontSize: 11, color: '#6b7280', lineHeight: 1.55 },
  footer: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '12px 24px',
    borderTop: '0.5px solid #e2ddd3',
    background: '#fafaf8',
  },
  checkLabel: {
    display: 'flex', alignItems: 'center', gap: 6,
    fontSize: 11, color: '#6b7280', cursor: 'pointer',
  },
  startBtn: {
    padding: '8px 20px', borderRadius: 6, border: 'none',
    background: '#1a1f2e', color: '#fff',
    fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
    transition: 'background 0.15s',
  },
  tipBox: {
    marginTop: 14, padding: '10px 14px',
    background: '#f3f8fb', border: '0.5px solid #c8e0ec',
    borderRadius: 8, fontSize: 11, color: '#5a9ab5', lineHeight: 1.5,
  },
};

export default function HelpModal({ onClose }) {
  const [dontShow, setDontShow] = useState(false);

  const handleClose = () => {
    if (dontShow) {
      localStorage.setItem('omapmaker_help_seen', '1');
    }
    onClose();
  };

  return (
    <div style={S.overlay} onClick={(e) => e.target === e.currentTarget && handleClose()}>
      <div style={S.modal}>
        <div style={S.header}>
          <div style={S.headerLeft}>
            <span style={S.dot} />
            <div>
              <div style={S.title}>Jak na to?</div>
              <div style={S.subtitle}>Generování map pro OB</div>
            </div>
          </div>
          <button style={S.closeBtn} onClick={handleClose}>×</button>
        </div>

        <div style={S.body}>
          <div style={S.stepsGrid}>
            {STEPS.map((step, i) => (
              <div style={S.step} key={i}>
                <div style={S.stepIcon}>{step.icon}</div>
                <div>
                  <div style={S.stepNum}>KROK {i + 1}</div>
                  <div style={S.stepTitle}>{step.title}</div>
                  <div style={S.stepDesc}>{step.desc}</div>
                </div>
              </div>
            ))}
          </div>

          <div style={S.tipBox}>
            💡 <strong>Tip:</strong> Pro oblast 3×3 km počítejte s 8 minutami zpracování.
            Větší oblasti se automaticky rozdělí na dlaždice. Data z ČÚZK jsou zdarma a pokrývají celou ČR.
          </div>
        </div>

        <div style={S.footer}>
          <label style={S.checkLabel}>
            <input
              type="checkbox"
              checked={dontShow}
              onChange={(e) => setDontShow(e.target.checked)}
            />
            Příště nezobrazovat
          </label>
          <button
            style={S.startBtn}
            onClick={handleClose}
            onMouseEnter={(e) => e.currentTarget.style.background = '#2d3448'}
            onMouseLeave={(e) => e.currentTarget.style.background = '#1a1f2e'}
          >
            Začít →
          </button>
        </div>
      </div>
    </div>
  );
}
