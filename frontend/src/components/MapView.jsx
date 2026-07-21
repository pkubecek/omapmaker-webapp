import React, { useEffect, useRef, useState, useCallback } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { startCuzkDownload, getCuzkStatus, startPolandDownload, getPolandStatus } from '../api';
import EUROPE_BORDERS from './europeBorders';

// Tooltip styl pro country polygony
if (typeof document !== 'undefined') {
  const s = document.createElement('style');
  s.textContent = [
    '.map-country-tooltip{background:rgba(26,31,46,0.82);color:#fff;border:none;',
    'box-shadow:none;font-family:monospace;font-size:11px;padding:3px 8px;',
    'border-radius:4px;white-space:nowrap;}',
    '.map-country-tooltip::before{display:none;}',
    '.leaflet-interactive{outline:none;}',
    '.leaflet-interactive:focus{outline:none;}',
  ].join('');
  document.head.appendChild(s);
}

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

const S = {
  wrap: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  toolbar: {
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '8px 12px', background: 'var(--panel-bg)',
    borderBottom: '0.5px solid var(--panel-border)', flexShrink: 0, flexWrap: 'wrap',
  },
  toolBtn: {
    display: 'flex', alignItems: 'center', gap: 4, background: 'none',
    border: '0.5px solid var(--panel-border)', borderRadius: 'var(--radius-sm)',
    padding: '4px 10px', fontSize: 11, cursor: 'pointer',
    color: 'var(--text-secondary)', fontFamily: 'var(--sans)', transition: 'background 0.15s',
  },
  toolBtnActive: { background: '#f0ead6', color: 'var(--text-primary)', borderColor: '#d0c8b8' },
  divider: { width: '0.5px', height: 16, background: 'var(--panel-border)', margin: '0 2px', flexShrink: 0 },
  bboxInfo: { fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-secondary)' },
  mapContainer: { flex: 1, position: 'relative' },
  toolCtrl: {
    position: 'absolute', top: 10, left: 10, zIndex: 1000,
    display: 'flex', background: 'rgba(255,255,255,0.92)',
    border: '0.5px solid var(--panel-border)', borderRadius: 'var(--radius-sm)',
    boxShadow: '0 2px 8px rgba(0,0,0,0.15)', overflow: 'hidden',
  },
  toolCtrlBtn: {
    display: 'flex', alignItems: 'center', gap: 4, background: 'none',
    border: 'none', padding: '6px 10px', fontSize: 11, cursor: 'pointer',
    color: 'var(--text-secondary)', fontFamily: 'var(--sans)', transition: 'background 0.15s',
  },
  toolCtrlBtnActive: { background: '#f0ead6', color: 'var(--text-primary)' },
  rightStack: {
    position: 'absolute', top: 10, right: 10, zIndex: 1000,
    display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8,
  },
  helpBtn: {
    width: 40, height: 40, padding: 0, borderRadius: '50%',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: 'rgba(255,255,255,0.92)', border: '0.5px solid var(--panel-border)',
    boxShadow: '0 2px 8px rgba(0,0,0,0.15)', cursor: 'pointer',
    fontWeight: 600, fontSize: 17, color: 'var(--text-primary)', fontFamily: 'var(--sans)',
  },
  baseLayerCtrl: {
    display: 'flex', background: 'rgba(255,255,255,0.92)',
    border: '0.5px solid var(--panel-border)', borderRadius: 'var(--radius-sm)',
    boxShadow: '0 2px 8px rgba(0,0,0,0.15)', overflow: 'hidden',
  },
  baseLayerBtn: {
    display: 'flex', alignItems: 'center', gap: 4, background: 'none',
    border: 'none', padding: '6px 10px', fontSize: 11, cursor: 'pointer',
    color: 'var(--text-secondary)', fontFamily: 'var(--sans)', transition: 'background 0.15s',
  },
  baseLayerBtnActive: { background: '#f0ead6', color: 'var(--text-primary)' },
  zoomCtrl: {
    display: 'flex', flexDirection: 'column', background: 'rgba(255,255,255,0.92)',
    border: '0.5px solid var(--panel-border)', borderRadius: 'var(--radius-sm)',
    boxShadow: '0 2px 8px rgba(0,0,0,0.15)', overflow: 'hidden',
  },
  zoomBtn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 30, height: 30, background: 'none', border: 'none',
    fontSize: 16, fontWeight: 600, cursor: 'pointer',
    color: 'var(--text-primary)', fontFamily: 'var(--sans)', lineHeight: 1,
  },
  zoomDivider: { height: '0.5px', background: 'var(--panel-border)' },
  hint: {
    position: 'absolute', bottom: 12, left: '50%', transform: 'translateX(-50%)',
    background: 'rgba(26,31,46,0.82)', color: '#fff', fontFamily: 'var(--mono)',
    fontSize: 11, padding: '5px 14px', borderRadius: 20, pointerEvents: 'none',
    whiteSpace: 'nowrap', zIndex: 1000,
  },
  // ČÚZK inline panel
  cuzkPanel: {
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '6px 12px', background: '#f6f9f3',
    borderBottom: '0.5px solid #d0e0c0', flexShrink: 0, flexWrap: 'wrap',
  },
  cuzkLabel: { fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'var(--mono)' },
  cuzkSelect: {
    fontFamily: 'var(--mono)', fontSize: 11, padding: '3px 6px',
    borderRadius: 'var(--radius-sm)', border: '0.5px solid var(--panel-border)',
    background: '#fff', cursor: 'pointer',
  },
  cuzkBtn: {
    display: 'flex', alignItems: 'center', gap: 4, padding: '5px 12px',
    borderRadius: 'var(--radius-sm)', border: 'none', background: 'var(--rock)',
    color: '#fff', fontSize: 11, fontFamily: 'var(--mono)', cursor: 'pointer',
    transition: 'opacity 0.15s',
  },
  cuzkProgress: {
    flex: 1, display: 'flex', alignItems: 'center', gap: 8,
  },
  cuzkBarWrap: {
    flex: 1, height: 4, background: '#e0ddd5', borderRadius: 2, overflow: 'hidden', minWidth: 60,
  },
  cuzkBarFill: { height: '100%', background: 'var(--forest)', borderRadius: 2, transition: 'width 0.4s' },
  cuzkMsg: { fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-secondary)', whiteSpace: 'nowrap' },
};

function fmtCoord(v) { return v.toFixed(4); }

// Hrubá detekce země podle středu bbox (WGS84)

// Dostupné zdroje dat
const DATA_SOURCES = [
  { key: 'cz',  flag: '🇨🇿', label: 'ČÚZK',   sublabel: 'Česká republika',  available: true  },
  { key: 'pl',  flag: '🇵🇱', label: 'GUGiK',   sublabel: 'Polsko (Beta)',           available: true  },
  { key: 'sk',  flag: '🇸🇰', label: 'ÚGKK SR', sublabel: 'Slovensko',        available: false },
  { key: 'at',  flag: '🇦🇹', label: 'BEV',     sublabel: 'Rakousko',         available: false },
  { key: 'de',  flag: '🇩🇪', label: 'BKG',     sublabel: 'Německo',          available: false },
];

function CountryDropdown({ country, disabled, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  // Zavři při kliknutí mimo
  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const current = DATA_SOURCES.find(s => s.key === country) || DATA_SOURCES[0];

  const autoTag = null;

  return (
    <div ref={ref} style={{ position: 'relative', flexShrink: 0 }}>
      {/* Trigger tlačítko */}
      <button
        disabled={disabled}
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 5,
          padding: '4px 8px 4px 8px',
          fontFamily: 'var(--mono)', fontSize: 11,
          background: open ? 'var(--ink)' : '#fff',
          color: open ? '#fff' : 'var(--text-primary)',
          border: '0.5px solid var(--panel-border)',
          borderRadius: 'var(--radius-sm)',
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.6 : 1,
          transition: 'background 0.15s, color 0.15s',
          whiteSpace: 'nowrap',
        }}
      >
        <span style={{ fontSize: 14 }}>{current.flag}</span>
        <span>{current.label}</span>
        {autoTag}
        <span style={{ marginLeft: 2, opacity: 0.5, fontSize: 9 }}>▾</span>
      </button>

      {/* Dropdown menu */}
      {open && (
        <div style={{
          position: 'absolute',
          top: 'calc(100% + 4px)',
          left: 0,
          background: '#fff',
          border: '0.5px solid var(--panel-border)',
          borderRadius: 'var(--radius-md)',
          boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
          zIndex: 2000,
          minWidth: 180,
          overflow: 'hidden',
        }}>
          {DATA_SOURCES.map((src, i) => (
            <button
              key={src.key}
              disabled={!src.available}
              onClick={() => {
                if (!src.available) return;
                onChange(src.key);
                setOpen(false);
              }}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                width: '100%', padding: '8px 12px',
                border: 'none',
                borderBottom: i < DATA_SOURCES.length - 1 ? '0.5px solid var(--panel-border)' : 'none',
                background: src.key === country ? '#f0ead6' : 'transparent',
                cursor: src.available ? 'pointer' : 'not-allowed',
                opacity: src.available ? 1 : 0.38,
                textAlign: 'left',
                transition: 'background 0.12s',
              }}
              onMouseEnter={e => { if (src.available) e.currentTarget.style.background = src.key === country ? '#e8e0cc' : '#fafaf8'; }}
              onMouseLeave={e => { e.currentTarget.style.background = src.key === country ? '#f0ead6' : 'transparent'; }}
            >
              <span style={{ fontSize: 18, lineHeight: 1 }}>{src.flag}</span>
              <div>
                <div style={{
                  fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 500,
                  color: src.available ? 'var(--text-primary)' : 'var(--text-muted)',
                }}>
                  {src.label}
                  {!src.available && (
                    <span style={{ marginLeft: 6, fontSize: 9, color: 'var(--text-muted)', fontWeight: 400 }}>
                      připravujeme
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
                  {src.sublabel}
                </div>
              </div>
              {src.key === country && (
                <span style={{ marginLeft: 'auto', color: 'var(--forest)', fontSize: 12 }}>✓</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function MapView({ bbox, onBboxChange, onCuzkComplete, onHelp, isMobile }) {
  const mapRef = useRef(null);
  const leafletRef = useRef(null);
  const rectRef = useRef(null);
  const drawState = useRef({ drawing: false, start: null });
  const [tool, setTool] = useState('pan');
  const [selectClicked, setSelectClicked] = useState(false);
  const [helpClicked, setHelpClicked] = useState(false);

  // ČÚZK state
  const [dsmType, setDsmType] = useState('DMPOK');
  const [cuzkState, setCuzkState] = useState('idle'); // idle | downloading | done | error
  const [cuzkProgress, setCuzkProgress] = useState(0);
  const [cuzkMsg, setCuzkMsg] = useState('');

  // Detekovaná/ručně zvolená země
  const [country, setCountry] = useState('cz');

  // Podkladová vrstva mapy
  const [baseLayer, setBaseLayer] = useState('osm');
  const baseLayersRef = useRef({});

  useEffect(() => {
    if (!bbox) setCountry('cz');
  }, [bbox]);

  // Init map — přidej polygony hranic
  useEffect(() => {
    if (leafletRef.current) return;
    const map = L.map(mapRef.current, { center: [49.8, 15.5], zoom: 8, zoomControl: false });

    const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap', maxZoom: 19,
    });
    const ortofotoLayer = L.tileLayer.wms('https://ags.cuzk.gov.cz/arcgis1/services/ORTOFOTO/MapServer/WMSServer', {
      layers: '0',
      format: 'image/jpeg',
      version: '1.3.0',
      crs: L.CRS.EPSG3857,
      transparent: false,
      attribution: '© ČÚZK',
      maxZoom: 20,
    });
    baseLayersRef.current = { osm: osmLayer, ortofoto: ortofotoLayer };
    osmLayer.addTo(map);

    const layersRef = { current: [] };

    const styleAvail      = { color: '#ffffff00', weight: 1.5, dashArray: '4 3', fillColor: '#ffffff00', fillOpacity: 0.0, interactive: true };
    const styleComingSoon = { color: '#ffffff00',    weight: 1.2, dashArray: '3 4', fillColor: '#ffffff',    fillOpacity: 0.0, interactive: true };
    const styleOther      = { color: '#ffffff00',    weight: 0.8, dashArray: '2 4', fillColor: '#ffffff',    fillOpacity: 0.0, interactive: false };

    const entries = [
      ...EUROPE_BORDERS.available.map(e => ({ ...e, style: styleAvail,      tooltip: `${e.iso === 'CZ' ? '🇨🇿 ČÚZK' : '🇵🇱 GUGiK'} — data dostupná` })),
      ...EUROPE_BORDERS.coming_soon.map(e => ({ ...e, style: styleComingSoon, tooltip: `${e.name} — připravujeme` })),
      ...EUROPE_BORDERS.other.map(e => ({ ...e, style: styleOther,      tooltip: null })),
    ];

    entries.forEach(({ geometry, style, tooltip }) => {
      const layer = L.geoJSON(geometry, { style: () => style, interactive: !!tooltip });
      if (tooltip) {
        layer.bindTooltip(tooltip, { sticky: true, className: 'map-country-tooltip' });
        layer._tooltipContent = tooltip;  // ulož pro pozdější obnovení
      }
      layer.addTo(map);
      layersRef.current.push(layer);
    });

    // Ref na layers pro vypínání tooltipů
    map._countryLayers = layersRef.current;

    leafletRef.current = map;
    return () => { map.remove(); leafletRef.current = null; };
  }, []);

  // Přepínání podkladové vrstvy (mapa / ortofoto)
  useEffect(() => {
    const map = leafletRef.current;
    if (!map) return;
    Object.entries(baseLayersRef.current).forEach(([key, layer]) => {
      if (key === baseLayer) {
        if (!map.hasLayer(layer)) layer.addTo(map);
      } else if (map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
    });
  }, [baseLayer]);

  // Draw bbox
  useEffect(() => {
    const map = leafletRef.current;
    if (!map) return;
    if (rectRef.current) { rectRef.current.remove(); rectRef.current = null; }
    if (bbox) {
      rectRef.current = L.rectangle(
        [[bbox.min_lat, bbox.min_lon], [bbox.max_lat, bbox.max_lon]],
        { color: '#c96a3a', weight: 2, dashArray: '6 4', fillColor: '#c96a3a', fillOpacity: 0.07 }
      ).addTo(map);
    }
  }, [bbox]);

  // Vypni tooltips při výběru oblasti (tool=select)
  useEffect(() => {
    const map = leafletRef.current;
    if (!map || !map._countryLayers) return;
    map._countryLayers.forEach(layer => {
      if (tool === 'select') {
        layer.unbindTooltip();
      } else if (layer._tooltipContent) {
        layer.bindTooltip(layer._tooltipContent, { sticky: true, className: 'map-country-tooltip' });
      }
    });
  }, [tool]);

  // Tool mouse handlers
  useEffect(() => {
    const map = leafletRef.current;
    if (!map) return;
    const container = map.getContainer();

    if (tool === 'pan') {
      map.dragging.enable();
      container.style.cursor = '';
      return;
    }

    map.dragging.disable();
    container.style.cursor = 'crosshair';

    let startLatLng = null;
    let tempRect = null;

    // Pomocná funkce — převede touch pozici na LatLng
    function touchToLatLng(touch) {
      const rect = container.getBoundingClientRect();
      const point = L.point(
        touch.clientX - rect.left,
        touch.clientY - rect.top
      );
      return map.containerPointToLatLng(point);
    }

    function onMouseDown(e) {
      startLatLng = e.latlng;
      if (rectRef.current) { rectRef.current.remove(); rectRef.current = null; }
      if (tempRect) { tempRect.remove(); tempRect = null; }
      drawState.current.drawing = true;
      setCuzkState('idle');
      setCuzkProgress(0);
      setCuzkMsg('');
    }
    function onMouseMove(e) {
      if (!drawState.current.drawing || !startLatLng) return;
      if (tempRect) tempRect.remove();
      tempRect = L.rectangle([startLatLng, e.latlng], {
        color: '#c96a3a', weight: 1.5, dashArray: '5 3', fillOpacity: 0.05,
      }).addTo(map);
    }
    function onMouseUp(e) {
      if (!drawState.current.drawing || !startLatLng) return;
      drawState.current.drawing = false;
      if (tempRect) { tempRect.remove(); tempRect = null; }
      const b = {
        min_lat: Math.min(startLatLng.lat, e.latlng.lat),
        max_lat: Math.max(startLatLng.lat, e.latlng.lat),
        min_lon: Math.min(startLatLng.lng, e.latlng.lng),
        max_lon: Math.max(startLatLng.lng, e.latlng.lng),
      };
      if (b.max_lat - b.min_lat < 0.001 || b.max_lon - b.min_lon < 0.001) { startLatLng = null; return; }
      rectRef.current = L.rectangle(
        [[b.min_lat, b.min_lon], [b.max_lat, b.max_lon]],
        { color: '#c96a3a', weight: 2, dashArray: '6 4', fillOpacity: 0.07 }
      ).addTo(map);
      onBboxChange(b);
      startLatLng = null;
    }

    // Touch handlery pro mobil
    function onTouchStart(e) {
      if (e.touches.length !== 1) return;
      e.preventDefault();
      const latlng = touchToLatLng(e.touches[0]);
      if (rectRef.current) { rectRef.current.remove(); rectRef.current = null; }
      if (tempRect) { tempRect.remove(); tempRect = null; }
      startLatLng = latlng;
      drawState.current.drawing = true;
      setCuzkState('idle');
      setCuzkProgress(0);
      setCuzkMsg('');
    }
    function onTouchMove(e) {
      if (!drawState.current.drawing || !startLatLng || e.touches.length !== 1) return;
      e.preventDefault();
      const latlng = touchToLatLng(e.touches[0]);
      if (tempRect) tempRect.remove();
      tempRect = L.rectangle([startLatLng, latlng], {
        color: '#c96a3a', weight: 2, dashArray: '5 3', fillOpacity: 0.06,
      }).addTo(map);
    }
    function onTouchEnd(e) {
      if (!drawState.current.drawing || !startLatLng) return;
      e.preventDefault();
      drawState.current.drawing = false;
      const lastTouch = e.changedTouches[0];
      const latlng = touchToLatLng(lastTouch);
      if (tempRect) { tempRect.remove(); tempRect = null; }
      const b = {
        min_lat: Math.min(startLatLng.lat, latlng.lat),
        max_lat: Math.max(startLatLng.lat, latlng.lat),
        min_lon: Math.min(startLatLng.lng, latlng.lng),
        max_lon: Math.max(startLatLng.lng, latlng.lng),
      };
      if (b.max_lat - b.min_lat < 0.001 || b.max_lon - b.min_lon < 0.001) { startLatLng = null; return; }
      rectRef.current = L.rectangle(
        [[b.min_lat, b.min_lon], [b.max_lat, b.max_lon]],
        { color: '#c96a3a', weight: 2, dashArray: '6 4', fillOpacity: 0.07 }
      ).addTo(map);
      onBboxChange(b);
      startLatLng = null;
    }

    map.on('mousedown', onMouseDown);
    map.on('mousemove', onMouseMove);
    map.on('mouseup', onMouseUp);
    // Touch eventy přidáme přímo na container (ne přes Leaflet)
    container.addEventListener('touchstart', onTouchStart, { passive: false });
    container.addEventListener('touchmove', onTouchMove, { passive: false });
    container.addEventListener('touchend', onTouchEnd, { passive: false });

    return () => {
      map.off('mousedown', onMouseDown);
      map.off('mousemove', onMouseMove);
      map.off('mouseup', onMouseUp);
      container.removeEventListener('touchstart', onTouchStart);
      container.removeEventListener('touchmove', onTouchMove);
      container.removeEventListener('touchend', onTouchEnd);
      if (tempRect) tempRect.remove();
      container.style.cursor = '';
      map.dragging.enable();
    };
  }, [tool, onBboxChange]);

  const clearBbox = () => {
    if (rectRef.current) { rectRef.current.remove(); rectRef.current = null; }
    onBboxChange(null);
    setCuzkState('idle');
  };

  // ČÚZK stahování s pollingem
  const handleCuzkDownload = useCallback(async () => {
    if (!bbox || cuzkState === 'downloading') return;
    setCuzkState('downloading');
    setCuzkProgress(5);
    setCuzkMsg('Spouštím stahování...');

    let dlId = null;
    try {
      const { download_id } = await startCuzkDownload(bbox, dsmType);
      dlId = download_id;
    } catch (err) {
      setCuzkMsg(`Chyba: ${err.response?.data?.detail || err.message}`);
      setCuzkState('error');
      return;
    }

    // Polling každé 3 sekundy
    const poll = setInterval(async () => {
      try {
        const s = await getCuzkStatus(dlId);
        setCuzkProgress(s.progress || 0);
        setCuzkMsg(s.step || '');

        if (s.status === 'done') {
          clearInterval(poll);
          setCuzkState('done');
          setCuzkProgress(100);
          setCuzkMsg('✓ Hotovo');
          if (onCuzkComplete) onCuzkComplete(s.dmr_path, s.dmp_path, 'EPSG:5514', 'server_path');
        } else if (s.status === 'error') {
          clearInterval(poll);
          setCuzkMsg(`Chyba: ${s.error || s.step}`);
          setCuzkState('error');
        }
      } catch (pollErr) {
        clearInterval(poll);
        setCuzkMsg(`Chyba připojení: ${pollErr.message}`);
        setCuzkState('error');
      }
    }, 3000);
  }, [bbox, dsmType, cuzkState, onCuzkComplete]);

  // Polsko stahování s pollingem
  const handlePolandDownload = useCallback(async () => {
    if (!bbox || cuzkState === 'downloading') return;
    setCuzkState('downloading');
    setCuzkProgress(5);
    setCuzkMsg('Spouštím stahování z GUGiK...');

    let dlId = null;
    try {
      const { download_id } = await startPolandDownload(bbox, true);
      dlId = download_id;
    } catch (err) {
      setCuzkMsg(`Chyba: ${err.response?.data?.detail || err.message}`);
      setCuzkState('error');
      return;
    }

    const poll = setInterval(async () => {
      try {
        const s = await getPolandStatus(dlId);
        setCuzkProgress(s.progress || 0);
        setCuzkMsg(s.step || '');

        if (s.status === 'done') {
          clearInterval(poll);
          setCuzkMsg('Hotovo!');
          setCuzkState('done');
          setCuzkProgress(100);
          // Předej serverové cesty přímo — nepotřebujeme stahovat blob přes browser
          const dmrServerPath = s.dmr_path;
          const dmpServerPath = s.dmp_path || null;
          const crs = s.crs || 'EPSG:2180';
          if (onCuzkComplete) onCuzkComplete(dmrServerPath, dmpServerPath, crs, 'server_path');
        } else if (s.status === 'error') {
          clearInterval(poll);
          setCuzkMsg(`Chyba: ${s.error || s.step}`);
          setCuzkState('error');
        }
      } catch (pollErr) {
        clearInterval(poll);
        setCuzkMsg(`Chyba připojení: ${pollErr.message}`);
        setCuzkState('error');
      }
    }, 3000);
  }, [bbox, cuzkState, onCuzkComplete]);

  const bboxLabel = bbox
    ? `${fmtCoord(bbox.min_lat)}–${fmtCoord(bbox.max_lat)} N · ${fmtCoord(bbox.min_lon)}–${fmtCoord(bbox.max_lon)} E`
    : '';

  const kmLat = bbox ? ((bbox.max_lat - bbox.min_lat) * 111).toFixed(1) : null;
  const kmLon = bbox ? ((bbox.max_lon - bbox.min_lon) * 111 * Math.cos((bbox.min_lat + bbox.max_lat) / 2 * Math.PI / 180)).toFixed(1) : null;

  return (
    <div style={S.wrap}>
      {/* Toolbar — zobrazí se jen po výběru oblasti */}
      {bbox && (
        <div style={{
          ...S.toolbar,
          padding: isMobile ? '6px 8px' : '8px 12px',
          gap: isMobile ? 4 : 6,
        }}>
          <button style={{
            ...S.toolBtn,
            padding: isMobile ? '6px 8px' : '4px 10px',
          }} onClick={clearBbox}>×</button>
          {bboxLabel && !isMobile && (
            <span style={S.bboxInfo}>
              {bboxLabel}
              {kmLat && <span style={{ marginLeft: 6, color: 'var(--text-muted)' }}>~{kmLat}×{kmLon} km</span>}
            </span>
          )}
          <button
            style={{
              ...S.toolBtn,
              marginLeft: 'auto',
              width: 26, height: 26, padding: 0,
              borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: 500, fontSize: 12,
            }}
            onClick={onHelp}
            title="Jak na to?"
          >?</button>
        </div>
      )}

      {/* Download panel — zobrazí se po výběru oblasti */}
      {bbox && (
        <div style={{
          ...S.cuzkPanel,
          flexDirection: isMobile ? 'column' : 'row',
          alignItems: isMobile ? 'stretch' : 'center',
          gap: isMobile ? 6 : 8,
          padding: isMobile ? '8px 12px' : '6px 12px',
        }}>
          {isMobile && bboxLabel && (
            <span style={{ ...S.cuzkLabel, fontSize: 9 }}>{bboxLabel}</span>
          )}

          {/* Dropdown výběr zdroje dat */}
          <CountryDropdown
            country={country}
            disabled={cuzkState === 'downloading'}
            onChange={(c) => { setCountry(c); setCuzkState('idle'); }}
          />

          <div style={{ width: '0.5px', height: 16, background: 'var(--panel-border)', flexShrink: 0 }} />

          {/* CZ-specifické: výběr DSM typu */}
          {country === 'cz' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={S.cuzkLabel}>DSM:</span>
              <select
                style={S.cuzkSelect}
                value={dsmType}
                onChange={(e) => setDsmType(e.target.value)}
                disabled={cuzkState === 'downloading'}
              >
                <option value="DMPOK">DMP OK (doporučeno)</option>
                <option value="DMP1G">DMP 1G</option>
              </select>
            </div>
          )}

          {/* PL-specifické: info */}
          {country === 'pl' && (
            <span style={{ ...S.cuzkLabel, fontStyle: 'italic' }}>LiDAR · EPSG:2180</span>
          )}

          {/* Tlačítko stáhnout */}
          {cuzkState === 'idle' && (
            <button style={{
              ...S.cuzkBtn,
              width: isMobile ? '100%' : 'auto',
              padding: isMobile ? '8px 12px' : '5px 12px',
            }} onClick={country === 'cz' ? handleCuzkDownload : handlePolandDownload}>
              ↓ Stáhnout DMR + DMP
            </button>
          )}

          {cuzkState === 'downloading' && (
            <div style={S.cuzkProgress}>
              <div style={S.cuzkBarWrap}>
                <div style={{ ...S.cuzkBarFill, width: `${cuzkProgress}%` }} />
              </div>
              <span style={{ ...S.cuzkMsg, whiteSpace: isMobile ? 'normal' : 'nowrap' }}>{cuzkMsg}</span>
            </div>
          )}

          {cuzkState === 'done' && (
            <span style={{ ...S.cuzkMsg, color: 'var(--forest)' }}>✓ Staženo</span>
          )}

          {cuzkState === 'error' && (
            <>
              <span style={{ ...S.cuzkMsg, color: 'var(--rock)' }}>{cuzkMsg}</span>
              <button style={{ ...S.cuzkBtn, background: 'var(--text-secondary)' }}
                onClick={country === 'cz' ? handleCuzkDownload : handlePolandDownload}>
                Zkusit znovu
              </button>
            </>
          )}
        </div>
      )}

      {/* Mapa */}
      <div style={S.mapContainer}>
        <div ref={mapRef} style={{ width: '100%', height: '100%' }} />

        {/* Nástroje Posun/Výběr — plovoucí nad mapou, vlevo nahoře */}
        <div style={S.toolCtrl}>
          <button
            style={{ ...S.toolCtrlBtn, ...(tool === 'pan' ? S.toolCtrlBtnActive : {}) }}
            onClick={() => setTool('pan')}
          >{isMobile ? '✋' : '✋ Posun'}</button>
          <button
            className={!selectClicked ? 'select-pulse' : ''}
            style={{ ...S.toolCtrlBtn, ...(tool === 'select' ? S.toolCtrlBtnActive : {}) }}
            onClick={() => { setTool('select'); setSelectClicked(true); }}
          >{isMobile ? '⬜' : '⬜ Výběr oblasti'}</button>
        </div>

        {/* Podklad, zoom a nápověda — jeden svislý sloupec vpravo nahoře, bez ruční pixelové matematiky */}
        <div style={S.rightStack}>
          <div style={S.baseLayerCtrl}>
            <button
              style={{ ...S.baseLayerBtn, ...(baseLayer === 'osm' ? S.baseLayerBtnActive : {}) }}
              onClick={() => setBaseLayer('osm')}
            >{isMobile ? '🗺' : '🗺 Mapa'}</button>
            <button
              style={{ ...S.baseLayerBtn, ...(baseLayer === 'ortofoto' ? S.baseLayerBtnActive : {}) }}
              onClick={() => setBaseLayer('ortofoto')}
            >{isMobile ? '🛰' : '🛰 Ortofoto'}</button>
          </div>

          <div style={S.zoomCtrl}>
            <button style={S.zoomBtn} onClick={() => leafletRef.current && leafletRef.current.zoomIn()}>+</button>
            <div style={S.zoomDivider} />
            <button style={S.zoomBtn} onClick={() => leafletRef.current && leafletRef.current.zoomOut()}>−</button>
          </div>

          <button
            className={!helpClicked ? 'select-pulse' : ''}
            style={S.helpBtn}
            onClick={() => { setHelpClicked(true); onHelp(); }}
            title="Jak na to?"
          >?</button>
        </div>

        {tool === 'pan' && !bbox && (
          <div style={S.hint}>Vyberte oblast – nástroj Výběr oblasti</div>
        )}
        {tool === 'select' && !bbox && (
          <div style={S.hint}>Táhněte myší pro výběr oblasti — pak stáhněte data a ta se sama nahrají jako vstupní</div>
        )}
      </div>
    </div>
  );
}