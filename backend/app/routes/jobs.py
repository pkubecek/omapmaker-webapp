"""
routes/jobs.py — FastAPI endpointy pro správu jobů.
Joby se ukládají na disk (JSON) aby přežily restart kontejneru.
"""
import os
import uuid
import json
import shutil
import sys
import time
import asyncio

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.job_store import JOBS_DIR, job_path as _job_path, read_job as _read_job, write_job as _write_job
from ..core.cleanup import purge_job_inputs

router = APIRouter()
# Jeden job má ve špičce ~1,5–2 GB RAM → při 8 GB stačí 2 souběžné joby
# s rezervou (3 už riskovaly OOM). Lze přepsat proměnnou prostředí.
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))
_job_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

# Fronta (FIFO) jobů čekajících na volný slot — pro zobrazení pořadí uživateli.
# Stav je jen v paměti hlavního procesu (uvicorn běží s jedním workerem).
_waiting: list[str] = []
# Běžící subprocessy a zrušené joby — pro tlačítko „Zrušit“ (/jobs/{id}/cancel)
_running_procs: dict[str, asyncio.subprocess.Process] = {}
_cancelled_jobs: set[str] = set()


def _queue_position(job_id: str) -> int | None:
    try:
        return _waiting.index(job_id) + 1
    except ValueError:
        return None


def _write_queued(job_id: str):
    pos = _queue_position(job_id)
    if pos is None:
        return
    job = _read_job(job_id) or {}
    job.update({
        "status": "queued",
        "step": f"Ve frontě — {pos}. v pořadí, čeká na volný výpočetní slot",
    })
    _write_job(job_id, job)


def _cancelled_state(step: str) -> dict:
    return {
        "status": "cancelled",
        "progress": 0,
        "step": step,
        "error": "cancelled",
        "png_path": None,
        "gpkg_path": None,
    }
JOB_TIMEOUT_SECONDS = int(os.environ.get("JOB_TIMEOUT_SECONDS", "1800"))  # 30 min
RENDER_TIMEOUT_SECONDS = int(os.environ.get("RENDER_TIMEOUT_SECONDS", "600"))  # 10 min
async def _run_job_subprocess(job_id: str, job_dir: str):
        _waiting.append(job_id)
        try:
            if _job_semaphore.locked():
                _write_queued(job_id)
            await _job_semaphore.acquire()
        finally:
            if job_id in _waiting:
                _waiting.remove(job_id)
        # Ostatním čekajícím se posunulo pořadí
        for other in list(_waiting):
            _write_queued(other)

        try:
            # Job mohl být zrušen ještě ve frontě (než se vůbec spustil subprocess)
            if job_id in _cancelled_jobs:
                _cancelled_jobs.discard(job_id)
                _write_job(job_id, _cancelled_state("Zrušeno uživatelem (ve frontě)."))
                purge_job_inputs(job_dir)
                return

            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "app.core.run_job_process", job_id, job_dir,
                    cwd=os.getcwd(),
                )
                _running_procs[job_id] = proc
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
 
                if job_id in _cancelled_jobs:
                    # Zrušeno během běhu — cancel endpoint proces zabil,
                    # doplníme finální stav (přepíše, co si stihl zapsat subprocess).
                    _cancelled_jobs.discard(job_id)
                    _write_job(job_id, _cancelled_state("Zrušeno uživatelem."))
                    return

                if proc.returncode != 0:
                    job = _read_job(job_id) or {}
                    if job.get("status") not in ("done", "error", "cancelled"):
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
            finally:
                _running_procs.pop(job_id, None)
                # Nahrané LAS/LAZ už nejsou potřeba (re-render jede z cache
                # pickle) — smazat hned, ať nezabírají disk až do TTL úklidu.
                purge_job_inputs(job_dir)
        finally:
            _job_semaphore.release()


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
    pos = _queue_position(job_id)
    if pos is not None and job.get("status") == "queued":
        job["queue_position"] = pos
        job["queue_length"] = len(_waiting)
    return {"job_id": job_id, **job}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Zruší běžící nebo ve frontě čekající job. U hotového/chybného jobu no-op."""
    job = _read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nenalezen.")
    if job.get("status") in ("done", "error", "cancelled"):
        return {"job_id": job_id, **job}

    _cancelled_jobs.add(job_id)
    proc = _running_procs.get(job_id)
    if proc is not None and proc.returncode is None:
        # Běží — zabít; finální stav zapíše _run_job_subprocess po proc.wait()
        proc.kill()
    else:
        # Čeká ve frontě — hned označit; slot se při přidělení jen přeskočí
        if job_id in _waiting:
            _waiting.remove(job_id)
            for other in list(_waiting):
                _write_queued(other)
        _write_job(job_id, {**job, **_cancelled_state("Zrušeno uživatelem (ve frontě).")})

    updated = _read_job(job_id) or job
    return {"job_id": job_id, **updated}


@router.get("/jobs/{job_id}/preview")
async def get_preview(job_id: str):
    """Zmenšený náhled PNG pro web (miniatura v pravém panelu)."""
    job = _read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nenalezen.")
    if job["status"] != "done":
        raise HTTPException(status_code=425, detail="Job ještě není hotový.")
    path = job.get("preview_path") or job.get("png_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Náhled nenalezen.")
    return FileResponse(path, media_type="image/png")


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


@router.get("/jobs/{job_id}/vectors")
async def get_vectors(job_id: str):
    """GeoJSON se všemi vykreslenými prvky (properties: code, sym_key, group)
    pro klientský live náhled a výběr vrstev v LayerSelector/VectorPreview."""
    job = _read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nenalezen.")
    if job["status"] != "done":
        raise HTTPException(status_code=425, detail="Job ještě není hotový.")
    vectors_path = job.get("vectors_path")
    if not vectors_path or not os.path.exists(vectors_path):
        raise HTTPException(status_code=404, detail="Vektorová data nenalezena.")
    return FileResponse(vectors_path, media_type="application/geo+json")


@router.get("/jobs/{job_id}/colors")
async def get_colors(job_id: str):
    """Mapa {ISOM kód: hex barva} podle skutečně použité symbols*.xml —
    pro obarvení VectorPreview stejně jako finální PNG/OOM."""
    job = _read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nenalezen.")
    if job["status"] != "done":
        raise HTTPException(status_code=425, detail="Job ještě není hotový.")
    colors_path = job.get("colors_path")
    if not colors_path or not os.path.exists(colors_path):
        raise HTTPException(status_code=404, detail="Barevná mapa nenalezena.")
    return FileResponse(colors_path, media_type="application/json")


class RenderRequest(BaseModel):
    selected_codes: list[str] | None = None


@router.post("/jobs/{job_id}/render")
async def render_custom(job_id: str, body: RenderRequest):
    """Znovu vyrenderuje PNG z cache (bez opětovného zpracování LiDAR/OSM)
    s výběrem vrstev, který si uživatel proklikal v LayerSelectoru.

    Render běží v samostatném procesu (app.core.run_render_process) přes
    stejný semaphore jako joby — neblokuje event loop a paměť matplotlibu
    se po dokončení vrátí OS. Request čeká na výsledek, API kontrakt
    pro frontend zůstává stejný."""
    job = _read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nenalezen.")
    if job["status"] != "done":
        raise HTTPException(status_code=425, detail="Job ještě není hotový.")

    job_dir = os.path.join(JOBS_DIR, job_id)

    # Každý request má vlastní request/result soubor — souběžné rendery
    # stejného jobu si je nepřepíšou.
    req_id = uuid.uuid4().hex[:8]
    request_path = os.path.join(job_dir, f"render_{req_id}.json")
    result_path = os.path.join(job_dir, f"render_{req_id}_result.json")
    with open(request_path, "w") as f:
        json.dump({"selected_codes": body.selected_codes, "result_path": result_path}, f)

    proc = None
    try:
        async with _job_semaphore:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "app.core.run_render_process",
                job_id, job_dir, request_path,
                cwd=os.getcwd(),
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=RENDER_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise HTTPException(
                    status_code=504,
                    detail=f"Render překročil časový limit ({RENDER_TIMEOUT_SECONDS // 60} min).",
                )

        try:
            with open(result_path) as f:
                result = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            raise HTTPException(
                status_code=500,
                detail=f"Render proces skončil bez výsledku (kód {proc.returncode}).",
            )
    except asyncio.CancelledError:
        # Request zrušen (odpojený klient / shutdown) — neodcházet od běžícího procesu
        if proc is not None and proc.returncode is None:
            proc.kill()
            await proc.wait()
        raise
    finally:
        for p in (request_path, result_path):
            try:
                os.remove(p)
            except OSError:
                pass

    if not result.get("ok"):
        if result.get("cache_missing"):
            raise HTTPException(
                status_code=404,
                detail="Cache pro znovu-vyrenderování nenalezena (job byl vytvořen před touto funkcí, spusťte generování znovu).",
            )
        raise HTTPException(status_code=500, detail=f"Render selhal: {result.get('error')}")

    # Znovu načíst — během renderu se job.json mohl změnit
    job = _read_job(job_id) or job
    job["custom_png_path"] = result["png_path"]
    _write_job(job_id, job)

    return {"png_url": f"/api/jobs/{job_id}/custom_png?t={int(time.time())}"}


@router.get("/jobs/{job_id}/custom_png")
async def get_custom_png(job_id: str):
    job = _read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nenalezen.")
    custom_png_path = job.get("custom_png_path")
    if not custom_png_path or not os.path.exists(custom_png_path):
        raise HTTPException(status_code=404, detail="Vlastní PNG nenalezeno.")
    return FileResponse(custom_png_path, media_type="image/png",
                        filename=f"OMap_{job_id}_custom.png")


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