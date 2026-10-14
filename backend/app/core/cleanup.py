"""
core/cleanup.py — úklid JOBS_DIR.

Dvě věci:
  1) purge_job_inputs(job_dir) — hned po doběhnutí jobu (done/error/cancel/
     timeout) smaže VŠECHNY vstupy: nahrané DTM/DSM, nahrané SHP (+ sidecary),
     dočasné dlaždice a i stažená data z ČÚZK/GUGiK/BEV/SITR, ze kterých job
     četl (pokud je zrovna nepoužívá jiný běžící job). Re-render jede jen
     z cache pickle, vstupy už nejsou potřeba a jsou to největší soubory.
  2) purge_job_outputs(job_dir) — u jobu, který skončil chybou/zrušením/
     timeoutem, smaže hned i výstupy (zůstane jen job.json se stavem).
  3) cleanup_loop() — každou minutu maže výstupy hotových jobů, na které
     se nikdo nedívá (frontend posílá heartbeat, dokud má výsledek otevřený;
     při odchodu ze stránky / novém jobu volá /release a smaže se hned),
     a stažená data, ze kterých nikdo negeneroval.

Pozor: soubory v kontejneru se na Railway počítají do paměti (page cache),
proto se musí mazat co nejdřív, ne až po dni.

Stáří se počítá z mtime job.json / status.json (= poslední aktivita:
progress, done, re-render, heartbeat, stažení PNG/GPKG), ne z data vytvoření.

Env:
  OMAPMAKER_JOB_IDLE_MINUTES         (default 10, 0 = úklid vypnutý)
  OMAPMAKER_DOWNLOAD_IDLE_MINUTES    (default 30 — nepoužitá stažená data)
  OMAPMAKER_CLEANUP_INTERVAL_SECONDS (default 60)
"""
import os
import json
import time
import shutil
import asyncio

from .job_store import JOBS_DIR

JOB_TTL_SECONDS = float(os.environ.get("OMAPMAKER_JOB_IDLE_MINUTES", "10")) * 60
DOWNLOAD_TTL_SECONDS = float(os.environ.get("OMAPMAKER_DOWNLOAD_IDLE_MINUTES", "30")) * 60
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("OMAPMAKER_CLEANUP_INTERVAL_SECONDS", "60"))
# „Aktivní“ stav bez jakékoli aktivity déle než tohle = mrtvý proces
# (restart kontejneru uprostřed jobu). Job má timeout 30 min.
STALE_ACTIVE_SECONDS = 2 * 3600

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
    # Aktivní joby/downloady nikdy nemažeme. Pojistka: "aktivní" stav bez
    # aktivity déle než STALE_ACTIVE_SECONDS je pozůstatek procesu, který
    # zanikl (restart kontejneru uprostřed jobu) — smaže se normálně.
    return status in ACTIVE_STATUSES and age < STALE_ACTIVE_SECONDS


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

            if _is_active(status, age) or age <= DOWNLOAD_TTL_SECONDS:
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


def _download_dir_of(path: str) -> str | None:
    """Pro soubor uvnitř JOBS_DIR/<cuzk|poland|austria|italy>/<dl_id>/...
    vrátí cestu k adresáři <dl_id>, jinak None."""
    real = os.path.realpath(path)
    for sub in DOWNLOAD_SUBDIRS:
        base = os.path.realpath(os.path.join(JOBS_DIR, sub)) + os.sep
        if real.startswith(base):
            dl_id = real[len(base):].split(os.sep, 1)[0]
            if dl_id:
                return os.path.join(base, dl_id)
    return None


def _download_dirs_used_by_other_jobs(exclude_job_dir: str) -> set[str]:
    """Download adresáře, ze kterých čte jiný aktivní (queued/running) job."""
    used: set[str] = set()
    if not os.path.isdir(JOBS_DIR):
        return used
    exclude = os.path.realpath(exclude_job_dir)
    for name in os.listdir(JOBS_DIR):
        path = os.path.join(JOBS_DIR, name)
        if (name in DOWNLOAD_SUBDIRS or not os.path.isdir(path)
                or os.path.realpath(path) == exclude):
            continue
        status = (_read_json(os.path.join(path, "job.json")) or {}).get("status")
        if status not in ACTIVE_STATUSES:
            continue
        fp = _read_json(os.path.join(path, "file_paths.json")) or {}
        for key in ("dtm", "dsm"):
            d = _download_dir_of(fp[key]) if fp.get(key) else None
            if d:
                used.add(d)
    return used


def purge_job_inputs(job_dir: str):
    """Po doběhnutí jobu smaže všechny jeho vstupy (viz docstring modulu).
    V adresáři jobu zůstanou jen výstupy (PNG, GPKG, vectors, colors, cache
    pro re-render) a malé JSONy — ty uklidí TTL."""
    # Dočasné body po dlaždicích z pipeline (při pádu/zrušení jobu tam zůstanou)
    shutil.rmtree(os.path.join(job_dir, "_tiles_tmp"), ignore_errors=True)

    fp = _read_json(os.path.join(job_dir, "file_paths.json")) or {}
    job_prefix = os.path.realpath(job_dir) + os.sep

    # --- DTM/DSM: upload v adresáři jobu, nebo serverová cesta z downloadu ---
    download_dirs: set[str] = set()
    for key in ("dtm", "dsm"):
        path = fp.get(key)
        if not path:
            continue
        real = os.path.realpath(path)
        if not real.startswith(job_prefix):
            d = _download_dir_of(real)
            if d:
                download_dirs.add(d)
            continue
        try:
            os.remove(real)
        except FileNotFoundError:
            pass  # dsm == dtm (fallback bez DSM) → už smazáno
        except OSError as e:
            print(f"[cleanup] Nelze smazat {real}: {e}")

    # --- Stažená data (ČÚZK/GUGiK/...) — smazat, pokud je nepoužívá jiný job
    if download_dirs:
        in_use = _download_dirs_used_by_other_jobs(job_dir)
        for d in download_dirs - in_use:
            shutil.rmtree(d, ignore_errors=True)
            print(f"[cleanup] Smazána stažená data {d}")

    # --- Nahrané SHP (ZABAGED/ISOM) včetně sidecarů (.dbf/.shx/.prj/.cpg) ---
    for key in ("zabaged", "isom"):
        for shp in fp.get(key) or []:
            real = os.path.realpath(shp)
            if not real.startswith(job_prefix):
                continue
            stem = os.path.splitext(os.path.basename(real))[0]
            folder = os.path.dirname(real)
            try:
                names = os.listdir(folder)
            except OSError:
                continue
            for name in names:
                if os.path.splitext(name)[0] == stem:
                    try:
                        os.remove(os.path.join(folder, name))
                    except OSError:
                        pass


def purge_job_outputs(job_dir: str):
    """Smaže z adresáře jobu všechno kromě job.json (stav pro polling)."""
    try:
        names = os.listdir(job_dir)
    except OSError:
        return
    for name in names:
        if name == "job.json":
            continue
        path = os.path.join(job_dir, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                pass


def release_job(job_dir: str) -> bool:
    """Smaže celý adresář jobu, pokud job neběží. Vrací True, když smazal."""
    status = (_read_json(os.path.join(job_dir, "job.json")) or {}).get("status")
    if status in ACTIVE_STATUSES:
        return False
    purge_job_inputs(job_dir)
    shutil.rmtree(job_dir, ignore_errors=True)
    return True
