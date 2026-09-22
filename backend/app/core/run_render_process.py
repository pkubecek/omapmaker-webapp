"""
core/run_render_process.py — re-render PNG z cache v SAMOSTATNÉM procesu.
Stejný důvod jako run_job_process.py: matplotlib/GDAL paměť se po renderu
vrátí OS a render neblokuje event loop FastAPI.

Volání: python -m app.core.run_render_process <job_id> <job_dir> <request_json>

<request_json>: {"selected_codes": [...] | null, "result_path": "..."}
Výsledek zapíše do result_path:
  {"ok": true,  "png_path": "..."}
  {"ok": false, "cache_missing": bool, "error": "..."}

job.json nezapisuje — to dělá endpoint v hlavním procesu.
"""
import sys
import json
import os
import traceback


def _write_result(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def main():
    job_id, job_dir, request_path = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(request_path) as f:
        req = json.load(f)
    result_path = req["result_path"]

    try:
        from .pipeline import render_from_cache, _cache_path

        # Explicitní kontrola — FileNotFoundError z hloubi renderu
        # (např. chybějící symbols*.xml) nesmí vypadat jako chybějící cache.
        if not os.path.exists(_cache_path(job_dir, job_id)):
            _write_result(result_path, {"ok": False, "cache_missing": True,
                                        "error": "cache not found"})
            return

        result = render_from_cache(job_id, job_dir,
                                   selected_codes=req.get("selected_codes"))
        _write_result(result_path, {"ok": True, "png_path": result["png_path"]})
    except Exception as e:
        traceback.print_exc()
        _write_result(result_path, {"ok": False, "cache_missing": False,
                                    "error": str(e)})


if __name__ == "__main__":
    main()