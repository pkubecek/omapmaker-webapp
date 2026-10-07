import { useMemo } from 'react';

// Zjednodušené barvy podle skupiny — jen pro orientaci v náhledu,
// přesnou ISOM kartografii dělá až serverový PNG export.
const GROUP_COLOR = {
  contours: '#c07a30',
  rocks: '#000000',
  water: '#2f7fd6',
  vegetation: '#2f8f4e',
  roads: '#8a1f1f',
  man_made: '#000000',
  buildings: '#000000',
  private: '#b08d57',
  other: '#888888',
};

export const MAP_PAPER = '#faf8f2';
const CONTENT_W = 1000; // šířka obsahu v jednotkách SVG (výška podle poměru stran)

export function symbolColor(code, group, symbolColors) {
  return (symbolColors && symbolColors[code]) || GROUP_COLOR[group] || '#555';
}

const toPoints = (ring, project) => ring.map(([x, y]) => project(x, y).join(',')).join(' ');
// Polygon s dírami jako jedna cesta (evenodd)
const polyPath = (rings, project) =>
  rings.map((r) => 'M' + r.map(([x, y]) => project(x, y).join(',')).join('L') + 'Z').join('');

const NS = { vectorEffect: 'non-scaling-stroke' };

function geomToElements(geom, color, project, key, out) {
  switch (geom.type) {
    case 'Point': {
      const [x, y] = project(...geom.coordinates);
      out.points.push(<circle key={key} cx={x} cy={y} r={1.4} fill={color} />);
      break;
    }
    case 'MultiPoint':
      geom.coordinates.forEach((c, i) => {
        const [x, y] = project(...c);
        out.points.push(<circle key={`${key}-${i}`} cx={x} cy={y} r={1.4} fill={color} />);
      });
      break;
    case 'LineString':
      out.lines.push(<polyline key={key} points={toPoints(geom.coordinates, project)} fill="none" stroke={color} strokeWidth={1.1} strokeLinejoin="round" style={NS} />);
      break;
    case 'MultiLineString':
      geom.coordinates.forEach((line, i) => out.lines.push(
        <polyline key={`${key}-${i}`} points={toPoints(line, project)} fill="none" stroke={color} strokeWidth={1.1} strokeLinejoin="round" style={NS} />,
      ));
      break;
    case 'Polygon':
      out.areas.push(<path key={key} d={polyPath(geom.coordinates, project)} fillRule="evenodd" fill={color} fillOpacity={0.45} stroke={color} strokeOpacity={0.7} strokeWidth={0.5} style={NS} />);
      break;
    case 'MultiPolygon':
      geom.coordinates.forEach((poly, i) => out.areas.push(
        <path key={`${key}-${i}`} d={polyPath(poly, project)} fillRule="evenodd" fill={color} fillOpacity={0.45} stroke={color} strokeOpacity={0.7} strokeWidth={0.5} style={NS} />,
      ));
      break;
    default:
      break;
  }
}

/**
 * Převod GeoJSON (v mapových metrech) na SVG prvky.
 * selectedCodes: Set<string> | null (null = vše)
 * Vrací { elements, width, height } — elements se vkládají do <svg> / MapCanvas.
 */
export function useVectorElements(vectorData, selectedCodes, symbolColors) {
  // Projekce a hranice závisí jen na datech, ne na výběru vrstev
  const geo = useMemo(() => {
    if (!vectorData?.features?.length) return null;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const collect = (c) => {
      if (typeof c[0] === 'number') {
        if (c[0] < minX) minX = c[0]; if (c[0] > maxX) maxX = c[0];
        if (c[1] < minY) minY = c[1]; if (c[1] > maxY) maxY = c[1];
      } else c.forEach(collect);
    };
    vectorData.features.forEach((f) => f.geometry && collect(f.geometry.coordinates));
    const spanX = Math.max(maxX - minX, 1e-6), spanY = Math.max(maxY - minY, 1e-6);
    const W = CONTENT_W, H = CONTENT_W * spanY / spanX;
    const project = (x, y) => [
      +(((x - minX) / spanX) * W).toFixed(2),
      +(H - ((y - minY) / spanY) * H).toFixed(2), // flip Y — mapové Y roste na sever
    ];
    return { W, H, project };
  }, [vectorData]);

  return useMemo(() => {
    if (!geo) return { elements: null, width: CONTENT_W, height: CONTENT_W };
    const out = { areas: [], lines: [], points: [] };
    vectorData.features.forEach((f, i) => {
      if (!f.geometry) return;
      const { code, group } = f.properties || {};
      if (selectedCodes !== null && selectedCodes !== undefined && !selectedCodes.has(code)) return;
      geomToElements(f.geometry, symbolColor(code, group, symbolColors), geo.project, i, out);
    });
    // Pořadí kreslení: plochy → linie → body (ať linie nezakryje výplň)
    return {
      elements: [
        <g key="areas">{out.areas}</g>,
        <g key="lines">{out.lines}</g>,
        <g key="points">{out.points}</g>,
      ],
      width: geo.W,
      height: geo.H,
    };
  }, [geo, vectorData, selectedCodes, symbolColors]);
}

/** Jednoduchý statický náhled (bez posunu/zoomu). */
export default function VectorPreview({ vectorData, selectedCodes, symbolColors }) {
  const { elements, width, height } = useVectorElements(vectorData, selectedCodes, symbolColors);
  if (!elements) return null;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: '100%', background: MAP_PAPER }}>
      {elements}
    </svg>
  );
}
