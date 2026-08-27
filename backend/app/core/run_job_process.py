"""
core/run_job_process.py — spouští se jako SAMOSTATNÝ proces (subprocess.Popen),
ne jako thread. Díky tomu se po dokončení jobu VEŠKERÁ paměť (GDAL cache,
numba, matplotlib, fragmentace haldy) vrátí zpět OS - proces prostě zanikne.

Volání: python -m app.core.run_job_process <job_id> <job_dir>

Očekává v <job_dir>:
  - params.json      (dict s parametry pipeline)
  - file_paths.json  (dict s cestami k DTM/DSM/ZABAGED/ISOM souborům)

Zapisuje průběžný i finální stav do job.json přes job_store.
"""
import sys
import json
import os
import traceback


def main():
    job_id = sys.argv[1]
    job_dir = sys.argv[2]

    from .job_store import write_job
    from .pipeline import run_pipeline

    with open(os.path.join(job_dir, "params.json")) as f:
        params = json.load(f)
    with open(os.path.join(job_dir, "file_paths.json")) as f:
        file_paths = json.load(f)

    def progress_cb(pct: int, msg: str):
        write_job(job_id, {
            "status": "running",
            "progress": pct,
            "step": msg,
            "error": None,
            "png_path": None,
            "gpkg_path": None,
        })

    try:
        result = run_pipeline(
            job_id=job_id,
            params=params,
            file_paths=file_paths,
            output_dir=job_dir,
            progress_cb=progress_cb,
        )
        write_job(job_id, {
            "status": "done",
            "progress": 100,
            "step": "Hotovo!",
            "error": None,
            "png_path": result.get("png_path"),
            "gpkg_path": result.get("gpkg_path"),
            "vectors_path": result.get("vectors_path"),
            "colors_path": result.get("colors_path"),
        })
    except Exception as e:
        traceback.print_exc()
        write_job(job_id, {
            "status": "error",
            "progress": 0,
            "step": f"Chyba: {e}",
            "error": str(e),
            "png_path": None,
            "gpkg_path": None,
        })


if __name__ == "__main__":
    main()