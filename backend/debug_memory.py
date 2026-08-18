"""
DOČASNÝ diagnostický endpoint - přilep do main.py, zavolej po pár minutách
klidu (žádný request), podívej se na výstup, pak zase smaž.
"""
import gc
import os
import tracemalloc

from fastapi import APIRouter

router = APIRouter()

# Zapni na startu appky (v main.py před `app = FastAPI()` přidej `tracemalloc.start()`)


@router.get("/debug/memory")
def debug_memory():
    import psutil

    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()

    gc.collect()
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics("lineno")[:15]

    return {
        "rss_mb": round(mem_info.rss / 1024 / 1024, 1),
        "vms_mb": round(mem_info.vms / 1024 / 1024, 1),
        "top_allocations": [
            {
                "location": str(stat.traceback),
                "size_mb": round(stat.size / 1024 / 1024, 2),
                "count": stat.count,
            }
            for stat in top_stats
        ],
    }
