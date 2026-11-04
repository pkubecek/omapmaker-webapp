"""
core/multi_source.py — automatický výběr zdrojů podle oblasti a spojení dat
přes státní hranice.

1. Z coverage.geojson se zjistí, které zdroje bbox protínají.
2. Výsledný CRS = nativní CRS zdroje, který pokrývá největší část bboxu.
3. Původní downloadery (ČÚZK, GUGiK, SITR) běží jako dosud; rastrové zdroje
   (Německo, Švýcarsko, Francie, Nizozemsko, Rakousko) se stáhnou rovnou do
   cílového CRS (raster_sources.download_raster).
4. Je-li zdrojů víc, LAZ se sloučí do jednoho souboru v cílovém CRS. Pořadí
   = priorita: body méně prioritního zdroje se vezmou jen tam, kde vyšší
   zdroj žádné body nemá (mřížka obsazenosti 4 m). V pásu podél hranice tak
   nevzniká "zubatý" povrch ze dvou překrývajících se měření.
"""

import os

import numpy as np
from pyproj import CRS, Transformer

from .cancellation import DownloadCancelled
from . import raster_sources as rs

LEGACY_EPSG = {"cz": 5514, "pl": 2180, "it-sicily": 25833}
GROUP_OF_LEGACY = {"cz": "cz", "pl": "pl", "it-sicily": "it"}
OCC_CELL_M = 4.0
MERGE_BUFFER_M = 50.0


def sources_for_bbox(bbox, group=None):
    """[(key, label, podíl plochy bboxu)] seřazené podle podílu."""
    from shapely.geometry import box
    b = box(bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"])
    bb = b.buffer(0.003)            # ~300 m — zachytí i hranici těsně vedle bboxu
    hits = []
    for key, grp, label, geom in rs.coverage():
        if group and grp != group:
            continue
        if geom.intersects(bb):
            share = geom.intersection(b).area / b.area if b.area else 0.0
            hits.append((key, label, share))
    hits.sort(key=lambda h: -h[2])
    return hits


def _native_epsg(key, bbox):
    return LEGACY_EPSG.get(key) or rs.native_epsg(key, bbox)


def _run_legacy(key, bbox, out_dir, dsm_type, cb, cancel_check):
    os.makedirs(out_dir, exist_ok=True)
    if key == "cz":
        from .downloader import download_cuzk
        r = download_cuzk(bbox=bbox, dsm_type=dsm_type, out_dir=out_dir,
                          progress_cb=cb, cancel_check=cancel_check)
        r.setdefault("crs", "EPSG:5514")
        return r
    if key == "pl":
        from .poland_downloader import download_poland
        return download_poland(bbox=bbox, out_dir=out_dir, progress_cb=cb, cancel_check=cancel_check)
    if key == "it-sicily":
        from .italy_downloader import download_italy
        return download_italy(bbox=bbox, out_dir=out_dir, progress_cb=cb, cancel_check=cancel_check)
    raise KeyError(key)


# ---------------------------------------------------------------------------
# Slučování LAZ
# ---------------------------------------------------------------------------

def _horizontal(crs):
    if crs.is_compound:
        for sub in crs.sub_crs_list:
            if sub.is_projected or sub.is_geographic:
                return sub
    return crs


def merge_laz(inputs, out_path, target_epsg, clip, cb=None, cancel_check=None):
    """
    inputs: [(path, default_epsg)] v pořadí priority.
    clip: (minx, miny, maxx, maxy) v target_epsg.
    Zapíše LAZ (point format 0) s x, y, z, classification.
    """
    import laspy
    from scipy.ndimage import binary_dilation

    minx, miny, maxx, maxy = clip
    W = int(np.ceil((maxx - minx) / OCC_CELL_M)) + 1
    H = int(np.ceil((maxy - miny) / OCC_CELL_M)) + 1
    occupied = np.zeros((H, W), dtype=bool)
    target = CRS.from_epsg(target_epsg)

    header = laspy.LasHeader(point_format=0, version="1.2")
    header.scales = np.array([0.01, 0.01, 0.01])
    header.offsets = np.array([minx, miny, 0.0])
    header.add_crs(target)
    total = 0

    with laspy.open(out_path, mode="w", header=header) as writer:
        for path, default_epsg in inputs:
            if not path or not os.path.exists(path):
                continue
            added = np.zeros_like(occupied)
            n_src = 0
            with laspy.open(path) as fh:
                try:
                    src_crs = fh.header.parse_crs()
                except Exception:
                    src_crs = None
                src_crs = _horizontal(src_crs) if src_crs is not None else CRS.from_epsg(default_epsg)
                tr = None if src_crs.equals(target) else \
                    Transformer.from_crs(src_crs, target, always_xy=True)
                swap = None
                for chunk in fh.chunk_iterator(1_000_000):
                    if cancel_check and cancel_check():
                        raise DownloadCancelled()
                    x = np.asarray(chunk.x, dtype=np.float64)
                    y = np.asarray(chunk.y, dtype=np.float64)
                    z = np.asarray(chunk.z, dtype=np.float64)
                    c = np.asarray(chunk.classification, dtype=np.uint8)
                    if swap is None:
                        # Pořadí os se u některých zdrojů (GUGiK) liší — vyber
                        # podle výsledku tu orientaci, která padne do oblasti.
                        def inside(a, b):
                            if tr:
                                a, b = tr.transform(a, b)
                            return int(((a >= minx) & (a <= maxx) & (b >= miny) & (b <= maxy)).sum())
                        s = slice(0, 20000)
                        swap = inside(y[s], x[s]) > inside(x[s], y[s])
                    if swap:
                        x, y = y, x
                    if tr:
                        x, y = tr.transform(x, y)
                    m = (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy) & np.isfinite(z)
                    if not m.any():
                        continue
                    x, y, z, c = x[m], y[m], z[m], c[m]
                    ci = ((x - minx) / OCC_CELL_M).astype(np.int64)
                    ri = ((y - miny) / OCC_CELL_M).astype(np.int64)
                    keep = ~occupied[ri, ci]
                    if not keep.any():
                        continue
                    x, y, z, c, ci, ri = x[keep], y[keep], z[keep], c[keep], ci[keep], ri[keep]
                    added[ri, ci] = True
                    pts = laspy.ScaleAwarePointRecord.zeros(x.size, header=header)
                    pts.x, pts.y, pts.z = x, y, z
                    pts.classification = np.minimum(c, 31)
                    writer.write_points(pts)
                    n_src += x.size
            total += n_src
            if cb:
                cb(f"  {os.path.basename(path)}: {n_src:,} bodů")
            # o jednu buňku rozšířit, ať se zdroje na hranici neprolínají
            occupied |= binary_dilation(added, iterations=1)
    return total


# ---------------------------------------------------------------------------
# Hlavní funkce
# ---------------------------------------------------------------------------

def download_auto(bbox, out_dir, dsm_type="DMPOK", group=None, progress_cb=None, cancel_check=None):
    """
    Stáhne DMR + DMP pro bbox ze všech zdrojů, které ho pokrývají
    (nebo jen ze skupiny `group`, např. "de"), a spojí je.
    Vrací {dmr_path, dmp_path, crs}.
    """
    os.makedirs(out_dir, exist_ok=True)

    def cb(msg):
        print(f"[auto] {msg}")
        if progress_cb:
            progress_cb(msg)

    hits = sources_for_bbox(bbox, group)
    if not hits:
        raise RuntimeError("Pro vybranou oblast nejsou dostupná výšková data.")
    keys = [k for k, _, _ in hits]
    target_epsg = _native_epsg(keys[0], bbox)
    cb("Zdroje: " + ", ".join(lbl for _, lbl, _ in hits) + f" → EPSG:{target_epsg}")

    results = []                      # [(key, result)] v pořadí priority
    raster_keys = [k for k in keys if rs.is_raster_key(k)]
    raster_done = False
    for key in keys:
        if cancel_check and cancel_check():
            raise DownloadCancelled()
        try:
            if rs.is_raster_key(key):
                if raster_done:
                    continue
                raster_done = True
                r = rs.download_raster(bbox, os.path.join(out_dir, "raster"), raster_keys,
                                       target_epsg, progress_cb=cb, cancel_check=cancel_check)
                results.append(("raster", r))
            else:
                r = _run_legacy(key, bbox, os.path.join(out_dir, key), dsm_type, cb, cancel_check)
                results.append((key, r))
        except DownloadCancelled:
            raise
        except Exception as e:
            if len(keys) == 1:
                raise
            cb(f"Varování: zdroj {key} selhal ({e}) — pokračuji s ostatními")

    results = [(k, r) for k, r in results if r.get("dmr_path")]
    if not results:
        raise RuntimeError("Žádný zdroj nevrátil DMR.")
    if len(results) == 1:
        k, r = results[0]
        return {"dmr_path": r["dmr_path"], "dmp_path": r.get("dmp_path") or "",
                "crs": r.get("crs") or f"EPSG:{target_epsg}"}

    def default_epsg(k, r):
        if r.get("crs"):
            return CRS.from_user_input(r["crs"]).to_epsg()
        return LEGACY_EPSG.get(k, target_epsg)

    clip = rs.bbox_bounds(target_epsg, bbox, MERGE_BUFFER_M)
    cb("Spojuji DMR ze všech zdrojů...")
    dmr_path = os.path.join(out_dir, "AUTO_DMR_merged.laz")
    n = merge_laz([(r["dmr_path"], default_epsg(k, r)) for k, r in results],
                  dmr_path, target_epsg, clip, cb, cancel_check)
    if n == 0:
        raise RuntimeError("Po spojení nezůstal v oblasti žádný bod DMR.")

    dmp_inputs = [(r["dmp_path"], default_epsg(k, r)) for k, r in results
                  if r.get("dmp_path") and str(r["dmp_path"]).lower().endswith((".las", ".laz"))]
    dmp_path = ""
    if dmp_inputs:
        cb("Spojuji DMP ze všech zdrojů...")
        dmp_path = os.path.join(out_dir, "AUTO_DMP_merged.laz")
        if merge_laz(dmp_inputs, dmp_path, target_epsg, clip, cb, cancel_check) == 0:
            dmp_path = ""

    # dílčí soubory už nepotřebujeme
    import shutil
    for k, _ in results:
        shutil.rmtree(os.path.join(out_dir, k), ignore_errors=True)

    cb("Hotovo — data spojena přes hranice.")
    return {"dmr_path": dmr_path, "dmp_path": dmp_path, "crs": f"EPSG:{target_epsg}"}
