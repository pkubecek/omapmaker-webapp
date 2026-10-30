import axios from 'axios';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({ baseURL: BASE });

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export async function startJob(formData, params) {
  formData.append('params', JSON.stringify(params));
  const res = await api.post('/api/jobs', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function getJobStatus(jobId) {
  const res = await api.get(`/api/jobs/${jobId}`);
  return res.data;
}

export async function cancelJob(jobId) {
  const res = await api.post(`/api/jobs/${jobId}/cancel`);
  return res.data;
}

// Dokud je výsledek otevřený, frontend posílá heartbeat — jinak backend
// výstupy jobu po pár minutách smaže (viz backend/app/core/cleanup.py).
export async function heartbeatJob(jobId) {
  const res = await api.post(`/api/jobs/${jobId}/heartbeat`);
  return res.data;
}

// Okamžité smazání výsledku na serveru (nový job / odchod ze stránky).
// sendBeacon projde i při zavírání záložky, kdy axios request nedoběhne.
export function releaseJob(jobId) {
  if (!jobId) return;
  const url = `${BASE}/api/jobs/${jobId}/release`;
  try {
    if (navigator.sendBeacon && navigator.sendBeacon(url)) return;
  } catch { /* fallback níže */ }
  api.post(`/api/jobs/${jobId}/release`).catch(() => {});
}

// Stažení souboru z backendu bez navigace stránky. Odkaz <a href download>
// na jinou doménu (backend) atribut download ignoruje a stránku naviguje —
// když backend vrátí chybu (404/500 JSON), prohlížeč odejde na chybovou
// stránku, spustí se 'pagehide' → releaseJob() a job se na serveru smaže.
export async function downloadFile(url, filename) {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* ne-JSON */ }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objUrl;
  a.download = filename || '';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objUrl), 10000);
}

export function getPreviewUrl(jobId) {
  return `${BASE}/api/jobs/${jobId}/preview`;
}

export function getPngUrl(jobId) {
  return `${BASE}/api/jobs/${jobId}/png`;
}

// selectedCodes: null = vše, jinak Set/pole kódů z výběru vrstev
export function getGpkgUrl(jobId, selectedCodes = null) {
  const url = `${BASE}/api/jobs/${jobId}/gpkg`;
  if (selectedCodes === null || selectedCodes === undefined) return url;
  const codes = Array.from(selectedCodes).sort().join(',');
  return `${url}?codes=${encodeURIComponent(codes)}`;
}

export function getVectorsUrl(jobId) {
  return `${BASE}/api/jobs/${jobId}/vectors`;
}

export function getColorsUrl(jobId) {
  return `${BASE}/api/jobs/${jobId}/colors`;
}

export async function renderCustomPng(jobId, selectedCodes) {
  const res = await api.post(`/api/jobs/${jobId}/render`, {
    selected_codes: selectedCodes,
  });
  // Backend vrací relativní cestu ("/api/jobs/{id}/custom_png?t=...") —
  // doplníme BASE, ať funguje i když frontend (Vercel) a backend (Railway)
  // běží na jiné doméně.
  const raw = res.data?.png_url || '';
  const png_url = raw.startsWith('http') ? raw : `${BASE}${raw}`;
  return { ...res.data, png_url };
}

// ---------------------------------------------------------------------------
// ČÚZK (Česká republika)
// ---------------------------------------------------------------------------

export async function startCuzkDownload(bbox, dsmType) {
  const res = await api.post('/api/download/cuzk', { bbox, dsm_type: dsmType });
  return res.data;
}

export async function getCuzkStatus(downloadId) {
  const res = await api.get(`/api/download/cuzk/${downloadId}`);
  return res.data;
}

export function getDmrUrl(downloadId) {
  return `${BASE}/api/download/cuzk/${downloadId}/dmr`;
}

export function getDmpUrl(downloadId) {
  return `${BASE}/api/download/cuzk/${downloadId}/dmp`;
}

export async function cancelCuzkDownload(downloadId) {
  const res = await api.post(`/api/download/cuzk/${downloadId}/cancel`);
  return res.data;
}

/** @deprecated */
export async function downloadCuzk(bbox, dsmType) {
  const res = await api.post('/api/download/cuzk', { bbox, dsm_type: dsmType });
  return res.data;
}

// ---------------------------------------------------------------------------
// GUGiK (Polsko)
// ---------------------------------------------------------------------------

export async function startPolandDownload(bbox, useLidar = true) {
  const res = await api.post('/api/download/poland', {
    bbox,
    use_lidar_point_cloud: useLidar,
  });
  return res.data;
}

export async function getPolandStatus(downloadId) {
  const res = await api.get(`/api/download/poland/${downloadId}`);
  return res.data;
}

export async function cancelPolandDownload(downloadId) {
  const res = await api.post(`/api/download/poland/${downloadId}/cancel`);
  return res.data;
}

// ---------------------------------------------------------------------------
// BEV (Rakousko)
// ---------------------------------------------------------------------------

export async function startAustriaDownload(bbox) {
  const res = await api.post('/api/download/austria', { bbox });
  return res.data;
}

export async function getAustriaStatus(downloadId) {
  const res = await api.get(`/api/download/austria/${downloadId}`);
  return res.data;
}

// ---------------------------------------------------------------------------
// SITR (Sicílie, Itálie)
// ---------------------------------------------------------------------------

export async function startItalyDownload(bbox) {
  const res = await api.post('/api/download/italy', { bbox });
  return res.data;
}

export async function getItalyStatus(downloadId) {
  const res = await api.get(`/api/download/italy/${downloadId}`);
  return res.data;
}

export async function cancelItalyDownload(downloadId) {
  const res = await api.post(`/api/download/italy/${downloadId}/cancel`);
  return res.data;
}