import React from 'react';

const styles = {
  bar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 16px',
    height: 48,
    background: '#fff',
    color: 'var(--text-primary)',
    fontFamily: 'var(--heading)',
    fontSize: 13,
    flexShrink: 0,
    borderBottom: '3px solid transparent',
    borderImage: 'var(--brand-gradient) 1',
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    fontWeight: 700,
    fontSize: 15,
    letterSpacing: '0.01em',
  },
  logo: {
    width: 28,
    height: 28,
    borderRadius: 7,
    flexShrink: 0,
  },
  version: { opacity: 0.35, fontWeight: 400 },
  status: { fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'var(--mono)' },
  actions: { display: 'flex', gap: 8 },
  btn: {
    background: 'none',
    border: '0.5px solid var(--panel-border)',
    color: 'var(--text-primary)',
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
    background: 'var(--brand-gradient)',
    borderColor: 'transparent',
    color: '#fff',
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
        <img src={`${process.env.PUBLIC_URL}/logo64.png`} alt="" style={styles.logo} />
        OMapMaker
        <span style={styles.version}></span>
      </div>
      <span style={styles.status}>{status}</span>
    </div>
  );
}
