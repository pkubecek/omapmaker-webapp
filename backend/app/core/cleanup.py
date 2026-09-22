"""
core/cleanup.py — úklid JOBS_DIR.

Dvě věci:
  1) purge_job_inputs(job_dir) — hned po doběhnutí jobu smaže nahrané DTM/DSM
     (LAS/LAZ) z adresáře jobu. Re-render jede jen z cache pickle, vstupy už
     nejsou potřeba a jsou to největší soubory v adresáři.
  2) cleanup_loop() — periodicky maže adresáře jobů a stažených dat
     (cuzk/poland/austria/italy), které jsou starší než TTL.

Stáří se počítá z mtime job.json / status.json (= poslední aktivita:
progress, done, re-render), ne z data vytvoření.

Env:
  OMAPMAKER_JOB_TTL_HOURS            (default 24, 0 = úklid vypnutý)
  OMAPMAKER_CLEANUP_INTERVAL_SECONDS (default 3600)
"""
import os
import json
import time
import shutil
import asyncio

from .job_store import JOBS_DIR

JOB_TTL_SECONDS = float(os.environ.get("OMAPMAKER_JOB_TTL_HOURS", "24")) * 3600
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("OMAPMAKER_CLEANUP_INTERVAL_SECONDS", "3600"))

# Podadresáře JOBS_DIR, které používá routes/download.py (JOBS_BASE + "/<zdroj>").
# Nejsou to joby, mají vlastní status.json a uklízejí se zvlášť.
DOWNLOAD_SUBDIRS = ("cuzk", "poland", "austria", "italy")

ACTIVE_STATUSES = ("queued", "running")


def _read_json(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _age_seconds(marker_path: str, dir_path: str, now: float) -> float:
    """Stáří podle mtime status souboru; když chybí, podle mtime adresáře."""
    for p in (marker_path, dir_path):
        try:
            return now - os.path.getmtime(p)
        except OSError:
            continue
    return 0.0


def _is_active(status: str | None, age: float) -> bool:
    # Aktivní joby/downloady nikdy nemažeme. Pojistka: "aktivní" stav starší
    # než 2×TTL je pozůstatek procesu, který zanikl (restart kontejneru
    # uprostřed jobu) — ten už nikdo nedokončí, takže se smaže normálně.
    return status in ACTIVE_STATUSES and age < 2 * JOB_TTL_SECONDS


def cleanup_expired(now: float | None = None) -> list[str]:
    """Smaže expirované adresáře jobů a downloadů. Vrací seznam smazaných cest."""
    if JOB_TTL_SECONDS <= 0 or not os.path.isdir(JOBS_DIR):
        return []
    now = now or time.time()
    removed: list[str] = []

    # --- Joby ---------------------------------------------------------------
    # Soubory, které právě používá aktivní job (DTM/DSM ze serverové cesty
    # v download adresáři) — ty download adresáře se nesmí smazat.
    protected_files: set[str] = set()
    expired_jobs: list[str] = []

    for name in os.listdir(JOBS_DIR):
        path = os.path.join(JOBS_DIR, name)
        if name in DOWNLOAD_SUBDIRS or not os.path.isdir(path):
            continue
        marker = os.path.join(path, "job.json")
        status = (_read_json(marker) or {}).get("status")
        age = _age_seconds(marker, path, now)

        if _is_active(status, age):
            fp = _read_json(os.path.join(path, "file_paths.json")) or {}
            for key in ("dtm", "dsm"):
                if fp.get(key):
                    protected_files.add(os.path.realpath(fp[key]))
            continue
        if age > JOB_TTL_SECONDS:
            expired_jobs.append(path)

    for path in expired_jobs:
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path)

    # --- Stažená data (ČÚZK / GUGiK / BEV / SITR) ----------------------------
    for sub in DOWNLOAD_SUBDIRS:
        base = os.path.join(JOBS_DIR, sub)
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            path = os.path.join(base, name)
            if not os.path.isdir(path):
                continue
            marker = os.path.join(path, "status.json")
            status = (_read_json(marker) or {}).get("status")
            age = _age_seconds(marker, path, now)

            if _is_active(status, age) or age <= JOB_TTL_SECONDS:
                continue
            prefix = os.path.realpath(path) + os.sep
            if any(p.startswith(prefix) for p in protected_files):
                continue
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path)

    return removed


async def cleanup_loop():
    """Běží na pozadí po celou dobu života appky (spouští se z main.py)."""
    if JOB_TTL_SECONDS <= 0:
        print("[cleanup] OMAPMAKER_JOB_TTL_HOURS=0 — úklid vypnutý.")
        return
    while True:
        try:
            # rmtree velkých LAZ adresářů blokuje → mimo event loop
            removed = await asyncio.to_thread(cleanup_expired)
            if removed:
                print(f"[cleanup] Smazáno {len(removed)} adresářů: "
                      + ", ".join(os.path.basename(p) for p in removed))
        except Exception as e:
            print(f"[cleanup] Chyba úklidu: {e}")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


def purge_job_inputs(job_dir: str):
    """Smaže nahrané DTM/DSM z adresáře jobu. Soubory mimo job_dir
    (serverové cesty z download adresářů) nechává být — ty uklidí TTL."""
    fp = _read_json(os.path.join(job_dir, "file_paths.json")) or {}
    job_prefix = os.path.realpath(job_dir) + os.sep
    for key in ("dtm", "dsm"):
        path = fp.get(key)
        if not path:
            continue
        real = os.path.realpath(path)
        if not real.startswith(job_prefix):
            continue
        try:
            os.remove(real)
        except FileNotFoundError:
            pass  # dsm == dtm (fallback bez DSM) → už smazáno
        except OSError as e:
            print(f"[cleanup] Nelze smazat {real}: {e}")