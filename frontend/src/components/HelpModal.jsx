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
    background: 'rgba(15,42,54,0.6)',
    zIndex: 9999,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  modal: {
    background: 'var(--panel-bg)',
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
    borderBottom: 'none',
    background: 'var(--brand-gradient)',
    color: '#fff',
  },
  headerLeft: { display: 'flex', alignItems: 'center', gap: 10 },
  dot: { width: 8, height: 8, borderRadius: '50%', background: '#fff', flexShrink: 0 },
  title: { fontFamily: 'var(--heading)', fontSize: 15, fontWeight: 700, letterSpacing: '0.01em' },
  subtitle: { fontSize: 11, opacity: 0.85, fontFamily: 'IBM Plex Mono, monospace', marginTop: 2 },
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
    borderRadius: 8, background: 'var(--surface)',
    border: '0.5px solid var(--panel-border)',
  },
  stepIcon: {
    fontSize: 22, flexShrink: 0, width: 36, height: 36,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: 'var(--accent-soft)', borderRadius: 8,
  },
  stepNum: {
    fontFamily: 'IBM Plex Mono, monospace', fontSize: 9,
    color: 'var(--accent-strong)', fontWeight: 600, letterSpacing: '0.06em',
    marginBottom: 3,
  },
  stepTitle: { fontSize: 12, fontWeight: 500, marginBottom: 5, color: 'var(--text-primary)' },
  stepDesc: { fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.55 },
  footer: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '12px 24px',
    borderTop: '0.5px solid var(--panel-border)',
    background: 'var(--surface)',
  },
  checkLabel: {
    display: 'flex', alignItems: 'center', gap: 6,
    fontSize: 11, color: 'var(--text-secondary)', cursor: 'pointer',
  },
  startBtn: {
    padding: '8px 20px', borderRadius: 6, border: 'none',
    background: 'var(--brand-gradient)', color: '#fff',
    fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
    transition: 'background 0.15s',
  },
  tipBox: {
    marginTop: 14, padding: '10px 14px',
    background: 'var(--info-soft-bg)', border: '0.5px solid var(--info-soft-border)',
    borderRadius: 8, fontSize: 11, color: 'var(--accent-strong)', lineHeight: 1.5,
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
            Větší oblasti se automaticky rozdělí na dlaždice.
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
            onMouseEnter={(e) => e.currentTarget.style.background = 'var(--brand-gradient-hover)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'var(--brand-gradient)'}
          >
            Začít →
          </button>
        </div>
      </div>
    </div>
  );
}
