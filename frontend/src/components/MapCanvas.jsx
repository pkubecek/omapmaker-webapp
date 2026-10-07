import React, { useCallback, useEffect, useRef } from 'react';

/**
 * SVG plátno s posunem a zoomem přes viewBox (zůstává vektorové a ostré
 * v libovolném přiblížení). Obsah (children) se kreslí v souřadnicích
 * 0..contentWidth × 0..contentHeight.
 *
 * Ovládání: kolečko = zoom ke kurzoru, tažení = posun, dvojklik = přiblížit,
 * dva prsty = pinch zoom, tlačítka +/−/⤢ vpravo dole.
 * resetKey: změna hodnoty vrátí pohled na celou mapu.
 */
const MAX_ZOOM = 60;   // max. přiblížení vůči celé mapě
const MIN_ZOOM = 0.5;

const btn = {
  width: 32, height: 32, border: '0.5px solid var(--panel-border)',
  background: 'var(--overlay-bg)', color: 'var(--text-primary)',
  fontSize: 16, lineHeight: 1, cursor: 'pointer', display: 'flex',
  alignItems: 'center', justifyContent: 'center', padding: 0,
};

export default function MapCanvas({ contentWidth, contentHeight, background = '#faf8f2', resetKey, children }) {
  const svgRef = useRef(null);
  const vb = useRef(null);
  const pointers = useRef(new Map());
  const lastPinch = useRef(null);

  const fullBox = useCallback(() => {
    const pad = Math.max(contentWidth, contentHeight) * 0.02;
    return { x: -pad, y: -pad, w: contentWidth + 2 * pad, h: contentHeight + 2 * pad };
  }, [contentWidth, contentHeight]);

  const apply = () => {
    const v = vb.current;
    if (svgRef.current && v) svgRef.current.setAttribute('viewBox', `${v.x} ${v.y} ${v.w} ${v.h}`);
  };

  const fit = useCallback(() => { vb.current = fullBox(); apply(); }, [fullBox]);

  useEffect(() => { fit(); }, [fit, resetKey]);

  // Klientské souřadnice → souřadnice obsahu
  const toContent = (clientX, clientY) => {
    const svg = svgRef.current;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const p = svg.createSVGPoint();
    p.x = clientX; p.y = clientY;
    return p.matrixTransform(ctm.inverse());
  };

  const zoomAt = (clientX, clientY, factor) => {
    const v = vb.current; const full = fullBox();
    const p = toContent(clientX, clientY);
    if (!v || !p) return;
    const newW = Math.min(Math.max(v.w / factor, full.w / MAX_ZOOM), full.w / MIN_ZOOM);
    const f = v.w / newW;
    vb.current = {
      x: p.x - (p.x - v.x) / f,
      y: p.y - (p.y - v.y) / f,
      w: newW,
      h: v.h / f,
    };
    apply();
  };

  const zoomCenter = (factor) => {
    const r = svgRef.current.getBoundingClientRect();
    zoomAt(r.left + r.width / 2, r.top + r.height / 2, factor);
  };

  // Kolečko — musí být non-passive, jinak nejde preventDefault (scroll stránky)
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return undefined;
    const onWheel = (e) => {
      e.preventDefault();
      const factor = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0018));
      zoomAt(e.clientX, e.clientY, factor);
    };
    svg.addEventListener('wheel', onWheel, { passive: false });
    return () => svg.removeEventListener('wheel', onWheel);
  });

  const onPointerDown = (e) => {
    svgRef.current.setPointerCapture(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    lastPinch.current = null;
  };

  const onPointerMove = (e) => {
    const pts = pointers.current;
    if (!pts.has(e.pointerId)) return;
    const prev = pts.get(e.pointerId);
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (pts.size === 1) {
      const ctm = svgRef.current.getScreenCTM();
      if (!ctm) return;
      const v = vb.current;
      v.x -= (e.clientX - prev.x) / ctm.a;
      v.y -= (e.clientY - prev.y) / ctm.d;
      apply();
    } else if (pts.size === 2) {
      const [a, b] = [...pts.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      const cx = (a.x + b.x) / 2, cy = (a.y + b.y) / 2;
      if (lastPinch.current) zoomAt(cx, cy, dist / lastPinch.current);
      lastPinch.current = dist;
    }
  };

  const onPointerUp = (e) => {
    pointers.current.delete(e.pointerId);
    lastPinch.current = null;
  };

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', background, overflow: 'hidden' }}>
      <svg
        ref={svgRef}
        width="100%" height="100%"
        preserveAspectRatio="xMidYMid meet"
        style={{ display: 'block', cursor: 'grab', touchAction: 'none', userSelect: 'none' }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDoubleClick={(e) => zoomAt(e.clientX, e.clientY, 2)}
      >
        {children}
      </svg>
      <div style={{
        position: 'absolute', right: 12, bottom: 12, display: 'flex', flexDirection: 'column',
        borderRadius: 'var(--radius-md)', overflow: 'hidden', boxShadow: '0 2px 8px var(--shadow)',
      }}>
        <button style={btn} onClick={() => zoomCenter(1.5)} title="Přiblížit">+</button>
        <button style={btn} onClick={() => zoomCenter(1 / 1.5)} title="Oddálit">−</button>
        <button style={{ ...btn, fontSize: 13 }} onClick={fit} title="Celá mapa">⤢</button>
      </div>
    </div>
  );
}
