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

@router.get("/debug/system")
def debug_system():
    """
    Ukáže CELÝ kontejner - všechny procesy, ne jen tenhle FastAPI proces.
    Pomůže odhalit osiřelé/zombie subprocessy z run_job_process.py,
    nebo potvrdit, že je to jen page cache (buff/cache), ne skutečně
    použitá paměť.
    """
    import psutil
 
    vm = psutil.virtual_memory()
 
    processes = []
    for p in psutil.process_iter(["pid", "ppid", "status", "cmdline", "memory_info", "create_time"]):
        try:
            info = p.info
            cmdline = " ".join(info["cmdline"] or [])
            if not cmdline:
                continue
            processes.append({
                "pid": info["pid"],
                "ppid": info["ppid"],
                "status": info["status"],
                "cmdline": cmdline[:150],
                "rss_mb": round(info["memory_info"].rss / 1024 / 1024, 1) if info["memory_info"] else None,
                "age_seconds": round(time.time() - info["create_time"], 1) if info["create_time"] else None,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
 
    processes.sort(key=lambda x: x["rss_mb"] or 0, reverse=True)
 
    return {
        "system_total_mb": round(vm.total / 1024 / 1024, 1),
        "system_used_mb": round(vm.used / 1024 / 1024, 1),
        "system_available_mb": round(vm.available / 1024 / 1024, 1),
        "system_cached_mb": round(getattr(vm, "cached", 0) / 1024 / 1024, 1),
        "system_buffers_mb": round(getattr(vm, "buffers", 0) / 1024 / 1024, 1),
        "process_count": len(processes),
        "processes": processes,
    }
 