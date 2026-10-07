import React, { useCallback, useEffect, useLayoutEffect, useState } from 'react';

/**
 * Průvodce rozhraním při první návštěvě.
 * Každý krok zvýrazní prvek s atributem data-tour="<target>" a vedle něj ukáže text.
 * Když prvek není vidět (mobil — jiná záložka, zavřený panel na tabletu),
 * zobrazí se karta uprostřed obrazovky bez zvýraznění.
 */
export const TOUR_SEEN_KEY = 'omapmaker_tour_seen';

const STEPS = [
  {
    target: 'select',
    title: 'Vyberte oblast',
    text: 'Klikněte na „Výběr oblasti“ a tažením myší vyznačte území, které chcete zmapovat. Nad mapou se pak objeví panel pro stažení DMR a DMP.',
  },
  {
    target: 'data',
    title: 'LiDAR data',
    text: 'Stažená data se sem vloží automaticky. Máte-li vlastní LiDAR (.las / .laz), přetáhněte ho sem.',
  },
  {
    target: 'settings',
    title: 'Nastavení mapy',
    text: 'Zvolte měřítko (1:4 000 sprint, 1:10 000, 1:15 000), formát papíru a parametry vrstevnic. U každé volby je nápověda pod ikonou „?“.',
  },
  {
    target: 'run',
    title: 'Generovat mapu',
    text: 'Až jsou data připravená, spusťte zpracování. Průběh a odhad zbývajícího času uvidíte hned pod tlačítkem.',
  },
  {
    target: 'output',
    title: 'Výsledek',
    text: 'Po dokončení se otevře mapa s vrstvami. Tady stáhnete PNG, GPKG pro OpenOrienteering Mapper i CRT tabulku symbolů.',
  },
];

const PAD = 6;        // okraj zvýraznění kolem prvku
const GAP = 14;       // mezera mezi zvýrazněním a kartou
const CARD_W = 300;

function visibleRect(el) {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  const vw = window.innerWidth, vh = window.innerHeight;
  if (r.width === 0 || r.height === 0) return null;
  if (r.right <= 0 || r.bottom <= 0 || r.left >= vw || r.top >= vh) return null;
  // Ořízni na viditelnou část okna (vysoké sekce)
  const top = Math.max(r.top, 8), bottom = Math.min(r.bottom, vh - 8);
  const left = Math.max(r.left, 8), right = Math.min(r.right, vw - 8);
  return { top, left, width: right - left, height: bottom - top };
}

function cardPosition(rect, cardH, isNarrow) {
  const vw = window.innerWidth, vh = window.innerHeight;
  if (!rect || isNarrow) return null; // → vycentrovat / dole
  const clampY = (y) => Math.min(Math.max(y, 12), vh - cardH - 12);
  const clampX = (x) => Math.min(Math.max(x, 12), vw - CARD_W - 12);
  const right = rect.left + rect.width + PAD + GAP;
  if (right + CARD_W < vw - 12) return { left: right, top: clampY(rect.top) };
  const left = rect.left - PAD - GAP - CARD_W;
  if (left > 12) return { left, top: clampY(rect.top) };
  const below = rect.top + rect.height + PAD + GAP;
  if (below + cardH < vh - 12) return { left: clampX(rect.left), top: below };
  return { left: clampX(rect.left), top: clampY(rect.top - PAD - GAP - cardH) };
}

const S = {
  blocker: { position: 'fixed', inset: 0, zIndex: 2500 },
  dim: { position: 'fixed', inset: 0, zIndex: 2500, background: 'rgba(8,22,28,0.6)' },
  spot: {
    position: 'fixed', zIndex: 2501, pointerEvents: 'none',
    borderRadius: 10, border: '2px solid var(--brand-blue)',
    boxShadow: '0 0 0 9999px rgba(8,22,28,0.6)',
    transition: 'top 0.25s ease, left 0.25s ease, width 0.25s ease, height 0.25s ease',
  },
  card: {
    position: 'fixed', zIndex: 2502, width: CARD_W, maxWidth: 'calc(100vw - 24px)',
    background: 'var(--panel-bg)', color: 'var(--text-primary)',
    borderRadius: 'var(--radius-lg)', boxShadow: '0 12px 40px rgba(0,0,0,0.35)',
    overflow: 'hidden', transition: 'top 0.25s ease, left 0.25s ease',
  },
  bar: { height: 3, background: 'var(--brand-gradient)' },
  inner: { padding: '14px 16px 12px' },
  step: {
    fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em',
    color: 'var(--accent-strong)', fontWeight: 600, marginBottom: 4,
  },
  title: { fontFamily: 'var(--heading)', fontWeight: 700, fontSize: 15, marginBottom: 6 },
  text: { fontSize: 12, lineHeight: 1.55, color: 'var(--text-secondary)' },
  footer: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 14 },
  dots: { display: 'flex', gap: 5, flex: 1 },
  dot: (on) => ({
    width: on ? 14 : 6, height: 6, borderRadius: 3,
    background: on ? 'var(--brand-blue)' : 'var(--panel-border)', transition: 'width 0.2s',
  }),
  skip: {
    background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 11,
    cursor: 'pointer', padding: '6px 4px', fontFamily: 'var(--sans)',
  },
  back: {
    background: 'none', border: '0.5px solid var(--panel-border)', color: 'var(--text-primary)',
    borderRadius: 'var(--radius-md)', padding: '6px 10px', fontSize: 12, cursor: 'pointer',
    fontFamily: 'var(--sans)',
  },
  next: {
    background: 'var(--brand-gradient)', border: 'none', color: '#fff', fontWeight: 600,
    borderRadius: 'var(--radius-md)', padding: '6px 14px', fontSize: 12, cursor: 'pointer',
    fontFamily: 'var(--sans)',
  },
};

export default function Tour({ onFinish, isMobile }) {
  const [i, setI] = useState(0);
  const [rect, setRect] = useState(null);
  const [cardH, setCardH] = useState(170);
  const step = STEPS[i];
  const last = i === STEPS.length - 1;

  const measure = useCallback(() => {
    const el = document.querySelector(`[data-tour="${step.target}"]`);
    setRect(visibleRect(el));
  }, [step.target]);

  // Při změně kroku: dorolovat prvek do zobrazení (např. v levém panelu) a změřit
  useLayoutEffect(() => {
    const el = document.querySelector(`[data-tour="${step.target}"]`);
    if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
    measure();
    const t = setTimeout(measure, 300); // po případném přepočtu layoutu / animaci
    return () => clearTimeout(t);
  }, [step.target, measure]);

  useEffect(() => {
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [measure]);

  const finish = useCallback(() => {
    try { localStorage.setItem(TOUR_SEEN_KEY, '1'); } catch { /* ignore */ }
    onFinish();
  }, [onFinish]);

  const next = useCallback(() => (last ? finish() : setI((n) => n + 1)), [last, finish]);
  const back = useCallback(() => setI((n) => Math.max(0, n - 1)), []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') finish();
      else if (e.key === 'ArrowRight') next();
      else if (e.key === 'ArrowLeft') back();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [finish, next, back]);

  const isNarrow = isMobile || window.innerWidth < 640;
  const pos = cardPosition(rect, cardH, isNarrow);
  const cardStyle = pos
    ? { ...S.card, left: pos.left, top: pos.top }
    : isNarrow
      ? { ...S.card, left: 12, right: 12, bottom: 76, width: 'auto' } // nad spodní lištou záložek
      : { ...S.card, left: '50%', top: '50%', transform: 'translate(-50%, -50%)' };

  return (
    <>
      {rect ? (
        <>
          <div style={S.blocker} />
          <div style={{
            ...S.spot,
            top: rect.top - PAD, left: rect.left - PAD,
            width: rect.width + 2 * PAD, height: rect.height + 2 * PAD,
          }} />
        </>
      ) : (
        <div style={S.dim} />
      )}

      <div
        style={cardStyle}
        role="dialog"
        aria-label={`Průvodce, krok ${i + 1} z ${STEPS.length}`}
        ref={(el) => { if (el && Math.abs(el.offsetHeight - cardH) > 2) setCardH(el.offsetHeight); }}
      >
        <div style={S.bar} />
        <div style={S.inner}>
          <div style={S.step}>KROK {i + 1} / {STEPS.length}</div>
          <div style={S.title}>{step.title}</div>
          <div style={S.text}>{step.text}</div>
          <div style={S.footer}>
            <div style={S.dots}>
              {STEPS.map((_, n) => <span key={n} style={S.dot(n === i)} />)}
            </div>
            {!last && <button style={S.skip} onClick={finish}>Přeskočit</button>}
            {i > 0 && <button style={S.back} onClick={back}>Zpět</button>}
            <button style={S.next} onClick={next} autoFocus>{last ? 'Hotovo' : 'Další →'}</button>
          </div>
        </div>
      </div>
    </>
  );
}
