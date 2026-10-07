// Světlý / tmavý režim.
// Uložená volba ('light' | 'dark') má přednost; bez ní se řídí nastavením systému.
// Počáteční nastavení dělá inline skript v public/index.html (ať stránka neproblikne).
import { useEffect, useState } from 'react';

const KEY = 'omapmaker_theme';
const media = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(prefers-color-scheme: dark)')
  : null;

function readStored() {
  try { return localStorage.getItem(KEY); } catch { return null; }
}

function resolve() {
  const stored = readStored();
  if (stored === 'light' || stored === 'dark') return stored;
  return media && media.matches ? 'dark' : 'light';
}

function apply(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', theme === 'dark' ? '#15232A' : '#1DA8D8');
}

export function useTheme() {
  const [theme, setTheme] = useState(resolve);

  useEffect(() => { apply(theme); }, [theme]);

  // Bez uložené volby sleduj změnu systémového režimu
  useEffect(() => {
    if (!media) return;
    const onChange = () => { if (!readStored()) setTheme(resolve()); };
    media.addEventListener?.('change', onChange);
    return () => media.removeEventListener?.('change', onChange);
  }, []);

  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem(KEY, next); } catch { /* private mode apod. */ }
    setTheme(next);
  };

  return { theme, toggle };
}
