import React, { useMemo } from 'react';

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

function ringToPoints(ring, project) {
  return ring.map(([x, y]) => project(x, y).join(',')).join(' ');
}

function geomToElements(geom, code, group, project, key) {
  const color = GROUP_COLOR[group] || '#555';
  switch (geom.type) {
    case 'Point':
      { const [x, y] = project(...geom.coordinates); return <circle key={key} cx={x} cy={y} r={1.2} fill={color} />; }
    case 'MultiPoint':
      return geom.coordinates.map((c, i) => {
        const [x, y] = project(...c);
        return <circle key={`${key}-${i}`} cx={x} cy={y} r={1.2} fill={color} />;
      });
    case 'LineString':
      return <polyline key={key} points={ringToPoints(geom.coordinates, project)} fill="none" stroke={color} strokeWidth={0.6} />;
    case 'MultiLineString':
      return geom.coordinates.map((line, i) => (
        <polyline key={`${key}-${i}`} points={ringToPoints(line, project)} fill="none" stroke={color} strokeWidth={0.6} />
      ));
    case 'Polygon':
      return <polygon key={key} points={ringToPoints(geom.coordinates[0], project)} fill={color} fillOpacity={0.25} stroke={color} strokeWidth={0.4} />;
    case 'MultiPolygon':
      return geom.coordinates.map((poly, i) => (
        <polygon key={`${key}-${i}`} points={ringToPoints(poly[0], project)} fill={color} fillOpacity={0.25} stroke={color} strokeWidth={0.4} />
      ));
    default:
      return null;
  }
}

/**
 * vectorData: GeoJSON FeatureCollection (v mapových metrech, ne WGS84)
 * selectedCodes: Set<string> | null (null = zobrazit vše)
 */
export default function VectorPreview({ vectorData, selectedCodes }) {
  const { elements, viewBox } = useMemo(() => {
    if (!vectorData?.features?.length) return { elements: null, viewBox: '0 0 100 100' };

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const collectBounds = (coords) => {
      if (typeof coords[0] === 'number') {
        const [x, y] = coords;
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
      } else {
        coords.forEach(collectBounds);
      }
    };
    vectorData.features.forEach((f) => collectBounds(f.geometry.coordinates));

    const W = 800, H = 800 * (maxY - minY) / Math.max(maxX - minX, 1e-6);
    const project = (x, y) => [
      ((x - minX) / (maxX - minX)) * W,
      H - ((y - minY) / (maxY - minY)) * H,   // flip Y — mapové Y roste na sever
    ];

    const els = [];
    vectorData.features.forEach((f, i) => {
      const { code, group } = f.properties || {};
      if (selectedCodes !== null && !selectedCodes.has(code)) return;
      const el = geomToElements(f.geometry, code, group, project, i);
      if (el) els.push(el);
    });

    return { elements: els, viewBox: `0 0 ${W} ${H}` };
  }, [vectorData, selectedCodes]);

  if (!elements) return null;

  return (
    <svg viewBox={viewBox} style={{ width: '100%', height: '100%', background: '#faf8f2' }}>
      {elements}
    </svg>
  );
}
