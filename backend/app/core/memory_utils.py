"""
Po zpracování LiDAR dat (rasterio/numpy/GDAL) glibc alokátor nevrací
uvolněnou paměť zpátky OS - drží si ji "v rezervě". Tohle to vynutí.

Použití: v backend/app/core/pipeline.py, na konci run_pipeline(),
těsně před return, zavolej release_memory().
"""
import ctypes
import gc


def release_memory():
    gc.collect()
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        # malloc_trim je Linux/glibc specifický - na jiných platformách no-op
        pass