"""
routes/download.py — stahování dat z ČÚZK ATOM jako background job.
POST /api/download/cuzk          — spustí stahování, vrátí download_id
GET  /api/download/cuzk/{id}     — stav stahování
GET  /api/download/cuzk/{id}/dmr — stáhne DMR soubor
GET  /api/download/cuzk/{id}/dmp — stáhne DMP soubor
"""
import os
import uuid
import json
import threading
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.downloader import download_cuzk as _download_cuzk

router = APIRouter()

DOWNLOADS_DIR = os.environ.get("OMAPMAKER_JOBS_DIR", "./jobs") + "/cuzk"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)


def _status_path(dl_id):
    return os.path.join(DOWNLOADS_DIR, dl_id, "status.json")

def _read_status(dl_id):
    p = _status_path(dl_id)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)

def _write_status(dl_id, data):
    p = _status_path(dl_id)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f)


class BboxModel(BaseModel):
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float

class CuzkRequest(BaseModel):
    bbox: BboxModel
    dsm_type: str = "DMPOK"


@router.post("/download/cuzk")
async def start_cuzk_download(req: CuzkRequest):
    """Spustí stahování ČÚZK na pozadí, vrátí download_id."""
    dl_id = str(uuid.uuid4())[:8]
    out_dir = os.path.join(DOWNLOADS_DIR, dl_id)
    os.makedirs(out_dir, exist_ok=True)

    _write_status(dl_id, {
        "status": "running",
        "progress": 0,
        "step": "Spouštím stahování...",
        "dmr_path": None,
        "dmp_path": None,
        "error": None,
    })

    def _run():
        def cb(msg):
            s = _read_status(dl_id) or {}
            s["step"] = msg
            s["progress"] = min(s.get("progress", 0) + 5, 90)
            _write_status(dl_id, s)

        try:
            result = _download_cuzk(
                bbox=req.bbox.model_dump(),
                dsm_type=req.dsm_type,
                out_dir=out_dir,
                progress_cb=cb,
            )
            _write_status(dl_id, {
                "status": "done",
                "progress": 100,
                "step": "Hotovo!",
                "dmr_path": result.get("dmr_path"),
                "dmp_path": result.get("dmp_path"),
                "error": None,
            })
        except Exception as e:
            import traceback; traceback.print_exc()
            _write_status(dl_id, {
                "status": "error",
                "progress": 0,
                "step": f"Chyba: {e}",
                "dmr_path": None,
                "dmp_path": None,
                "error": str(e),
            })

    threading.Thread(target=_run, daemon=True).start()
    return {"download_id": dl_id}


@router.get("/download/cuzk/{dl_id}")
async def get_cuzk_status(dl_id: str):
    s = _read_status(dl_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Download nenalezen.")
    return {"download_id": dl_id, **s}


@router.get("/download/cuzk/{dl_id}/dmr")
async def get_dmr_file(dl_id: str):
    s = _read_status(dl_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Download nenalezen.")
    if s["status"] != "done":
        raise HTTPException(status_code=425, detail="Stahování ještě neskončilo.")
    path = s.get("dmr_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="DMR soubor nenalezen.")
    return FileResponse(path, media_type="application/octet-stream",
                        filename=os.path.basename(path))


@router.get("/download/cuzk/{dl_id}/dmp")
async def get_dmp_file(dl_id: str):
    s = _read_status(dl_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Download nenalezen.")
    if s["status"] != "done":
        raise HTTPException(status_code=425, detail="Stahování ještě neskončilo.")
    path = s.get("dmp_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="DMP soubor nenalezen.")
    return FileResponse(path, media_type="application/octet-stream",
                        filename=os.path.basename(path))
