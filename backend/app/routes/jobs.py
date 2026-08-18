"""
routes/jobs.py — FastAPI endpointy pro správu jobů.
Joby se ukládají na disk (JSON) aby přežily restart kontejneru.
"""
import os
import uuid
import json
import shutil
import sys
import asyncio

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse

from ..core.job_store import job_path as _job_path, read_job as _read_job, write_job as _write_job
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "3"))
_job_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
    JOB_TIMEOUT_SECONDS = int(os.environ.get("JOB_TIMEOUT_SECONDS", "1800"))  # 30 min
 
 
    async def _run_job_subprocess(job_id: str, job_dir: str):
        """
        Čeká na volný slot (max MAX_CONCURRENT_JOBS souběžně), pak spustí
        zpracování jako samostatný proces. Pokud job běží déle než
        JOB_TIMEOUT_SECONDS (typicky zaseklé stahování dat z ČÚZK/GUGiK),
        proces se násilně zabije, aby nedržel paměť navěky.
        """
        position_job = _read_job(job_id) or {}
        if _job_semaphore.locked():
            position_job["status"] = "queued"
            position_job["step"] = f"Ve frontě (max {MAX_CONCURRENT_JOBS} souběžných jobů)..."
            _write_job(job_id, position_job)
 
        async with _job_semaphore:
            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "app.core.run_job_process", job_id, job_dir,
                    cwd=os.getcwd(),
                )
                try:
                    await asyncio.wait_for(proc.wait(), timeout=JOB_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()  # počkej, ať se opravdu ukončí (zamezí zombie)
                    _write_job(job_id, {
                        "status": "error",
                        "progress": 0,
                        "step": f"Zpracování překročilo časový limit ({JOB_TIMEOUT_SECONDS // 60} min) a bylo ukončeno.",
                        "error": "timeout",
                        "png_path": None,
                        "gpkg_path": None,
                    })
                    return
 
                if proc.returncode != 0:
                    job = _read_job(job_id) or {}
                    if job.get("status") not in ("done", "error"):
                        _write_job(job_id, {
                            "status": "error",
                            "progress": 0,
                            "step": f"Proces skončil s chybou (kód {proc.returncode})",
                            "error": f"Exit code {proc.returncode}",
                            "png_path": None,
                            "gpkg_path": None,
                        })
            except Exception as e:
                if proc is not None and proc.returncode is None:
                    proc.kill()
                    await proc.wait()
                _write_job(job_id, {
                    "status": "error",
                    "progress": 0,
                    "step": f"Chyba spuštění: {e}",
                    "error": str(e),
                    "png_path": None,
                    "gpkg_path": None,
                })


def _save_file(upload: UploadFile, dest_dir: str) -> str:
    path = os.path.join(dest_dir, upload.filename)
    with open(path, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return path


@router.post("/jobs")
async def create_job(
    dtm: UploadFile = File(default=None),
    dsm: UploadFile = File(default=None),
    dtm_server_path: str = Form(default=None),
    dsm_server_path: str = Form(default=None),
    zabaged: list[UploadFile] = File(default=[]),
    zabaged_sidecar: list[UploadFile] = File(default=[]),
    isom: list[UploadFile] = File(default=[]),
    isom_sidecar: list[UploadFile] = File(default=[]),
    params: str = Form(...),
):
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    # DTM — buď serverová cesta nebo upload
    if dtm_server_path and os.path.exists(dtm_server_path):
        dtm_path = dtm_server_path
    elif dtm and dtm.filename:
        dtm_path = _save_file(dtm, job_dir)
    else:
        raise HTTPException(status_code=422, detail="Chybí DTM soubor nebo cesta.")

    # DSM — buď serverová cesta nebo upload (volitelný)
    if dsm_server_path and os.path.exists(dsm_server_path):
        dsm_path = dsm_server_path
    elif dsm and dsm.filename:
        dsm_path = _save_file(dsm, job_dir)
    else:
        dsm_path = dtm_path  # fallback: pipeline zvládne i bez DSM

    # Sidecar soubory (.dbf, .shx, .prj) ulož do stejné složky jako .shp
    # aby je geopandas/fiona při read_file() automaticky našlo podle názvu
    for f in zabaged_sidecar:
        if f.filename:
            _save_file(f, job_dir)
    for f in isom_sidecar:
        if f.filename:
            _save_file(f, job_dir)

    # .shp soubory — ty se předají do pipeline jako cesty
    zabaged_paths = [_save_file(f, job_dir) for f in zabaged if f.filename]
    isom_paths = [_save_file(f, job_dir) for f in isom if f.filename]

    try:
        params_dict = json.loads(params)
    except Exception:
        params_dict = {}

    _write_job(job_id, {
        "status": "queued",
        "progress": 0,
        "step": "Ve frontě...",
        "error": None,
        "png_path": None,
        "gpkg_path": None,
    })
 
    file_paths = {
        "dtm": dtm_path,
        "dsm": dsm_path,
        "zabaged": zabaged_paths,
        "isom": isom_paths,
    }
    # Parametry a cesty se předávají přes JSON soubory, subprocess
    # nesdílí Python paměť s hlavním procesem
    with open(os.path.join(job_dir, "params.json"), "w") as f:
        json.dump(params_dict, f)
    with open(os.path.join(job_dir, "file_paths.json"), "w") as f:
        json.dump(file_paths, f)
 
    # Naplánuje spuštění (respektuje MAX_CONCURRENT_JOBS limit),
    # request se hned vrátí - frontend pozná stav pollingem /jobs/{id}
    asyncio.create_task(_run_job_subprocess(job_id, job_dir))
 
    return {"job_id": job_id}

@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = _read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nenalezen.")
    return {"job_id": job_id, **job}


@router.get("/jobs/{job_id}/png")
async def get_png(job_id: str):
    job = _read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nenalezen.")
    if job["status"] != "done":
        raise HTTPException(status_code=425, detail="Job ještě není hotový.")
    png_path = job.get("png_path")
    if not png_path or not os.path.exists(png_path):
        raise HTTPException(status_code=404, detail="PNG nenalezeno.")
    return FileResponse(png_path, media_type="image/png", filename=f"OMap_{job_id}.png")


@router.get("/jobs/{job_id}/gpkg")
async def get_gpkg(job_id: str):
    job = _read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nenalezen.")
    if job["status"] != "done":
        raise HTTPException(status_code=425, detail="Job ještě není hotový.")
    gpkg_path = job.get("gpkg_path")
    if not gpkg_path or not os.path.exists(gpkg_path):
        raise HTTPException(status_code=404, detail="GPKG nenalezeno.")
    return FileResponse(gpkg_path, media_type="application/geopackage+sqlite3",
                        filename=f"OOM_{job_id}.gpkg")


@router.get("/crt/{filename}")
async def get_crt(filename: str):
    """Vrátí .crt soubor pro import do OpenOrienteering Mapperu."""
    for search_dir in [
        ".",
        os.path.join(os.path.dirname(__file__), "..", ".."),
        os.path.join(os.path.dirname(__file__), ".."),
    ]:
        path = os.path.join(search_dir, filename)
        if os.path.exists(path) and filename.endswith(".crt"):
            return FileResponse(path, media_type="application/octet-stream",
                                filename=filename)
    raise HTTPException(status_code=404, detail=f"Soubor {filename} nenalezen.")