"""
core/job_store.py — čtení/zápis stavu jobu na disk (JSON).
Vytaženo z routes/jobs.py, aby to šlo importovat i ze subprocess skriptu
(run_job_process.py) bez nutnosti importovat celou FastAPI appku.
"""
import os
import json

JOBS_DIR = os.environ.get("OMAPMAKER_JOBS_DIR", "./jobs")
os.makedirs(JOBS_DIR, exist_ok=True)


def job_path(job_id: str) -> str:
    return os.path.join(JOBS_DIR, job_id, "job.json")


def read_job(job_id: str) -> dict | None:
    path = job_path(job_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def write_job(job_id: str, data: dict):
    path = job_path(job_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
