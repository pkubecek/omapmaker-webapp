import React, { useState } from 'react';

const TABS = [
  { key: 'settings', label: 'Nastavení', icon: '⚙' },
  { key: 'map',      label: 'Mapa',      icon: '🗺' },
  { key: 'output',   label: 'Výstup',    icon: '📄' },
];

const S = {
  wrap: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'hidden',
    position: 'absolute',
    inset: 0,
  },
  content: {
    flex: 1,
    overflow: 'hidden',
    position: 'relative',
    minHeight: 0,
  },
  pane: (visible) => ({
    position: 'absolute',
    inset: 0,
    overflow: 'auto',
    display: visible ? 'flex' : 'none',
    flexDirection: 'column',
  }),
  tabBar: {
    display: 'flex',
    borderTop: '0.5px solid var(--panel-border)',
    background: 'var(--panel-bg)',
    flexShrink: 0,
    height: 56,
    paddingBottom: 'env(safe-area-inset-bottom)',
  },
  tab: (active) => ({
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
    border: 'none',
    background: 'none',
    cursor: 'pointer',
    fontSize: 10,
    fontFamily: 'var(--mono)',
    color: active ? 'var(--rock)' : 'var(--text-muted)',
    borderTop: active ? '2px solid var(--rock)' : '2px solid transparent',
    transition: 'color 0.15s',
    WebkitTapHighlightColor: 'transparent',
  }),
  tabIcon: { fontSize: 20, lineHeight: 1 },
};

export default function MobileLayout({ settingsPane, mapPane, outputPane }) {
  const [tab, setTab] = useState('map');

  return (
    <div style={S.wrap}>
      <div style={S.content}>
        <div style={S.pane(tab === 'settings')}>{settingsPane}</div>
        <div style={S.pane(tab === 'map')}>{mapPane}</div>
        <div style={S.pane(tab === 'output')}>{outputPane}</div>
      </div>

      <nav style={S.tabBar}>
        {TABS.map(t => (
          <button key={t.key} style={S.tab(tab === t.key)} onClick={() => setTab(t.key)}>
            <span style={S.tabIcon}>{t.icon}</span>
            {t.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
