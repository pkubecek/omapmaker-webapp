import React, { useState, useCallback, useRef } from 'react';
import Topbar from './components/Topbar';
import SettingsPanel from './components/SettingsPanel';
import MapView from './components/MapView';
import OutputPanel from './components/OutputPanel';
import CuzkDownloader from './components/CuzkDownloader';
import HelpModal from './components/HelpModal';
import MobileLayout from './components/MobileLayout';
import TabletLayout from './components/TabletLayout';
import { useBreakpoint } from './hooks/useBreakpoint';
import { startJob, getJobStatus } from './api';

const DEFAULT_SETTINGS = {
  crs: 'EPSG:5514',
  scale: '10000',
  paper: 'A4 na šířku',
  contourInterval: '5',
  sigma: '4',
  slopeThreshold: '45',
  northRotation: '5',
  bin1: '1',
  bin2: '2',
  bin3: '6',
  bin4: '12',
  // Prohlubně
  depMinDiameter: '2',
  depMaxDiameter: '5',
  depMinDepth: '0.7',
  // Kupky
  knoMinDiameter: '1.5',
  knoMaxDiameter: '10',
  knoMinHeight: '0.5',
  layers: {
    contours: true,
    rocks: true,
    water: true,
    vegetation: true,
    roads: true,
    buildings: true,
    man_made: true,
    magnetic_lines: false,
  },
  download_zabaged: false,
};

const DEFAULT_FILES = {
  dtm: null,
  dsm: null,
  zabaged: [],
  isom: [],
};

const PAPER_MAP = {
  'A4 na šířku': 'A4 (Landscape)',
  'A4 na výšku': 'A4 (Portrait)',
  'A3 na šířku': 'A3 (Landscape)',
  'A3 na výšku': 'A3 (Portrait)',
  'Extent dat': 'Data Extent',
};

function nowStr() {
  const d = new Date();
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, '0'))
    .join(':');
}

export default function App() {
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [files, setFiles] = useState(DEFAULT_FILES);
  const [bbox, setBbox] = useState(null);
  const [job, setJob] = useState({ status: 'idle', progress: 0, step: '', jobId: null });
  const [logLines, setLogLines] = useState([]);
  const [showHelp, setShowHelp] = useState(
    () => localStorage.getItem('omapmaker_help_seen') !== '1'
  );
  const pollRef = useRef(null);

  const addLog = useCallback((msg, type = 'info') => {
    setLogLines((prev) => [...prev.slice(-199), { time: nowStr(), msg, type }]);
  }, []);

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const pollJob = useCallback((jobId) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const data = await getJobStatus(jobId);
        setJob((prev) => ({
          ...prev,
          status: data.status,
          progress: data.progress ?? prev.progress,
          step: data.step ?? prev.step,
          jobId,
        }));
        if (data.step) addLog(data.step, data.status === 'error' ? 'warn' : 'info');
        if (data.status === 'done' || data.status === 'error') {
          stopPolling();
          if (data.status === 'done') addLog('Analýza dokončena.', 'ok');
          else addLog('Chyba: ' + (data.error || 'Neznámá chyba'), 'warn');
        }
      } catch (err) {
        addLog('Chyba při komunikaci se serverem.', 'warn');
      }
    }, 1500);
  }, [addLog]);

  const handleRun = useCallback(async () => {
    if (!files.dtm || !files.dsm) return;
    setLogLines([]);
    setJob({ status: 'queued', progress: 0, step: 'Odesílám data...', jobId: null });
    addLog('Spouštím analýzu...', 'info');

    const formData = new FormData();

    // Pokud soubory jsou na serveru (z ČÚZK/GUGiK downloadu), pošli jen cesty
    if (files.dtm?.serverPath) {
      formData.append('dtm_server_path', files.dtm.serverPath);
    } else {
      formData.append('dtm', files.dtm);
    }
    if (files.dsm?.serverPath) {
      formData.append('dsm_server_path', files.dsm.serverPath);
    } else if (files.dsm) {
      formData.append('dsm', files.dsm);
    }
    // Posílej jen .shp soubory jako 'zabaged' — backend je zpracuje přes gpd.read_file()
    // Sidecar soubory (.dbf, .shx, .prj) pošli zvlášť — backend je uloží do stejné složky
    (files.zabaged || []).forEach((f) => {
      if (f.name.toLowerCase().endsWith('.shp')) {
        formData.append('zabaged', f);
      } else {
        formData.append('zabaged_sidecar', f);
      }
    });
    (files.isom || []).forEach((f) => {
      if (f.name.toLowerCase().endsWith('.shp')) {
        formData.append('isom', f);
      } else {
        formData.append('isom_sidecar', f);
      }
    });

    const params = {
      crs: settings.crs,
      scale: parseInt(settings.scale),
      paper_format: PAPER_MAP[settings.paper] || settings.paper,
      contour_interval: parseFloat(settings.contourInterval),
      sigma: parseFloat(settings.sigma),
      slope_threshold: parseFloat(settings.slopeThreshold),
      north_rotation: parseFloat(settings.northRotation),
      bins: [
        parseFloat(settings.bin1),
        parseFloat(settings.bin2),
        parseFloat(settings.bin3),
        parseFloat(settings.bin4),
      ],
      depressions: {
        min_diameter: parseFloat(settings.depMinDiameter),
        max_diameter: parseFloat(settings.depMaxDiameter),
        min_depth: parseFloat(settings.depMinDepth),
      },
      knolls: {
        min_diameter: parseFloat(settings.knoMinDiameter),
        max_diameter: parseFloat(settings.knoMaxDiameter),
        min_height: parseFloat(settings.knoMinHeight),
      },
      layers: settings.layers,
      download_zabaged: !!settings.download_zabaged,
      bbox: bbox || null,
    };

    try {
      const { job_id } = await startJob(formData, params);
      addLog(`Job spuštěn: ${job_id}`, 'ok');
      setJob((prev) => ({ ...prev, status: 'running', jobId: job_id }));
      pollJob(job_id);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message;
      addLog('Chyba při spuštění: ' + msg, 'warn');
      setJob({ status: 'error', progress: 0, step: msg, jobId: null });
    }
  }, [files, settings, bbox, addLog, pollJob]);

  const handleCuzkComplete = useCallback((dmrPath, dmpPath, crs, mode) => {
    if (mode === 'server_path') {
      // Serverové cesty — nepotřebujeme File objekty
      addLog(`DTM načteno: ${dmrPath.split('/').pop()}`, 'ok');
      if (dmpPath) addLog(`DSM načteno: ${dmpPath.split('/').pop()}`, 'ok');
      else addLog('DSM nedostupný (pipeline použije jen DTM)', 'warn');
      setFiles(prev => ({ ...prev, dtm: { serverPath: dmrPath, name: dmrPath.split('/').pop() }, dsm: dmpPath ? { serverPath: dmpPath, name: dmpPath.split('/').pop() } : prev.dsm }));
    } else {
      // Fallback: File objekty (ruční upload)
      addLog(`DTM načteno: ${dmrPath.name} (${(dmrPath.size / 1e6).toFixed(1)} MB)`, 'ok');
      if (dmpPath) addLog(`DSM načteno: ${dmpPath.name} (${(dmpPath.size / 1e6).toFixed(1)} MB)`, 'ok');
      else addLog('DSM nedostupný (pipeline použije jen DTM)', 'warn');
      setFiles(prev => ({ ...prev, dtm: dmrPath, dsm: dmpPath || prev.dsm }));
    }
    if (crs && crs !== 'EPSG:5514') {
      setSettings(prev => ({ ...prev, crs }));
      addLog(`CRS nastaveno na ${crs}`, 'info');
    }
  }, [addLog]);

  const canRun = Boolean(files.dtm && files.dsm);
  const hasDtm = Boolean(files.dtm?.serverPath || (files.dtm && files.dtm.size > 0));
  const hasDsm = Boolean(files.dsm?.serverPath || (files.dsm && files.dsm.size > 0));
  const running = job.status === 'running' || job.status === 'queued';

  let topStatus = 'Připraveno';
  if (!hasDtm && !hasDsm) topStatus = 'Nahrajte DTM a DSM';
  else if (!hasDtm) topStatus = 'Chybí DTM';
  else if (!hasDsm) topStatus = 'Chybí DSM';
  else if (running) topStatus = 'Zpracovávám...';
  else if (job.status === 'done') topStatus = 'Mapa vygenerována ✓';
  else if (job.status === 'error') topStatus = 'Chyba!';
  else topStatus = 'Připraveno ke spuštění';

  const { isMobile, isTablet } = useBreakpoint();

  const settingsPane = (
    <SettingsPanel
      settings={settings}
      onSettings={setSettings}
      files={files}
      onFiles={setFiles}
      isMobile={isMobile}
    />
  );

  const mapPane = (
    <MapView
      bbox={bbox}
      onBboxChange={setBbox}
      onCuzkComplete={handleCuzkComplete}
      onHelp={() => setShowHelp(true)}
      isMobile={isMobile}
    />
  );

  const outputPane = (
    <OutputPanel
      job={job}
      logLines={logLines}
      canRun={canRun}
      running={running}
      onRun={handleRun}
      isMobile={isMobile}
    />
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <Topbar status={topStatus} isMobile={isMobile} />

      <div style={{ flex: 1, overflow: 'hidden', position: 'relative', minHeight: 0 }}>
        {isMobile ? (
          <MobileLayout
            settingsPane={settingsPane}
            mapPane={mapPane}
            outputPane={outputPane}
          />
        ) : isTablet ? (
          <TabletLayout
            settingsPane={settingsPane}
            mapPane={mapPane}
            outputPane={outputPane}
          />
        ) : (
          <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
            {settingsPane}
            {mapPane}
            {outputPane}
          </div>
        )}
      </div>

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} isMobile={isMobile} />}
    </div>
  );
}