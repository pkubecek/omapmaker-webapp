import React, { useState } from 'react';

const S = {
  wrap: { display: 'flex', height: '100%', overflow: 'hidden', position: 'relative' },
  drawer: (open) => ({
    position: 'absolute',
    left: 0, top: 0, bottom: 0,
    width: 'clamp(260px, 30vw, 360px)',
    zIndex: 200,
    transform: open ? 'translateX(0)' : 'translateX(-100%)',
    transition: 'transform 0.25s ease',
    boxShadow: open ? '4px 0 20px rgba(0,0,0,0.15)' : 'none',
    display: 'flex', flexDirection: 'column',
    background: 'var(--panel-bg)',
  }),
  overlay: (open) => ({
    position: 'absolute', inset: 0,
    background: 'rgba(26,31,46,0.3)',
    zIndex: 199,
    display: open ? 'block' : 'none',
  }),
  main: { flex: 1, display: 'flex', overflow: 'hidden' },
  hamburger: {
    position: 'absolute', top: 10, left: 10, zIndex: 201,
    width: 36, height: 36,
    background: 'var(--panel-bg)',
    border: '0.5px solid var(--panel-border)',
    borderRadius: 'var(--radius-sm)',
    cursor: 'pointer', fontSize: 16,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  },
};

export default function TabletLayout({ settingsPane, mapPane, outputPane }) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div style={S.wrap}>
      <button style={S.hamburger} onClick={() => setDrawerOpen(o => !o)}>
        {drawerOpen ? '×' : '☰'}
      </button>

      <div style={S.overlay(drawerOpen)} onClick={() => setDrawerOpen(false)} />

      <div style={S.drawer(drawerOpen)}>
        {settingsPane}
      </div>

      <div style={S.main}>
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {mapPane}
        </div>
        <div style={{ width: 'clamp(220px, 25vw, 300px)', flexShrink: 0, overflow: 'auto', borderLeft: '0.5px solid var(--panel-border)' }}>
          {outputPane}
        </div>
      </div>
    </div>
  );
}
