import React from 'react';

const styles = {
  bar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 16px',
    height: 48,
    background: 'var(--ink)',
    color: '#fff',
    fontFamily: 'var(--mono)',
    fontSize: 13,
    flexShrink: 0,
    borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    fontWeight: 500,
    letterSpacing: '0.06em',
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    background: 'var(--rock)',
    flexShrink: 0,
  },
  version: { opacity: 0.35, fontWeight: 400 },
  status: { fontSize: 11, opacity: 0.5, fontFamily: 'var(--mono)' },
  actions: { display: 'flex', gap: 8 },
  btn: {
    background: 'none',
    border: '0.5px solid rgba(255,255,255,0.22)',
    color: '#fff',
    padding: '5px 12px',
    borderRadius: 'var(--radius-sm)',
    fontSize: 11,
    fontFamily: 'var(--heading)',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: 5,
    transition: 'border-color 0.15s',
  },
  btnPrimary: {
    background: 'var(--rock)',
    borderColor: 'var(--rock)',
  },
  btnDisabled: {
    opacity: 0.4,
    cursor: 'not-allowed',
  },
};

export default function Topbar({ status }) {
  return (
    <div style={styles.bar}>
      <div style={styles.brand}>
        <span style={styles.dot} />
        OMapMaker
        <span style={styles.version}></span>
      </div>
      <span style={styles.status}>{status}</span>
    </div>
  );
}
