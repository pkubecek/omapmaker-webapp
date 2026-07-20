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

export function getPngUrl(jobId) {
  return `${BASE}/api/jobs/${jobId}/png`;
}

export function getGpkgUrl(jobId) {
  return `${BASE}/api/jobs/${jobId}/gpkg`;
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