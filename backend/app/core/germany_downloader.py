"""
core/germany_downloader.py — DTM (DGM1) a DSM (DOM) pro Bavorsko a Sasko.

Oba státy dávají výškopis jako open data po dlaždicích, jejichž URL se dá
spočítat ze souřadnic levého dolního rohu (km) — žádné WFS ani index.

  Bavorsko (LDBV, CC BY 4.0, EPSG:25832, dlaždice 1×1 km)
    DGM1: https://download1.bayernwolke.de/a/dgm/dgm1/{e}_{n}.tif           (1 m)
    DOM:  https://download1.bayernwolke.de/a/dom20/DOM/32{e}_{n}_20_DOM.tif (0.2 m, ~48 MB)

  Sasko (GeoSN, dl-de/by-2-0, EPSG:25833, dlaždice 2×2 km, sudé km)
    https://geocloud.landesvermessung.sachsen.de/public.php/dav/files/{token}/
        dgm1_33{e}_{n}_2_sn_tiff.zip   (1 m)
        dom1_33{e}_{n}_2_sn_tiff.zip   (1 m)
    Token sdílení je pevný pro produkt, ale GeoSN ho občas vymění. Když pro
    oblast v Sasku nepřijde ani jedna dlaždice, zkusí se aktuální tokeny
    vyčíst z konfigurace jejich prohlížeče (geoviewer .../produktdownload/app.json).

URL a tokeny převzaty z knihovny geokachel (ověřeno jejím autorem 2026-09-20).

Postup: dlaždice obou států, které protínají bbox, se stáhnou (paralelně, na
disk, po zpracování hned smazány), přeprojektují do společné 1m mřížky
(EPSG:25833 východně od 12° E, jinak 25832) a mozaika se zapíše jako LAZ —
DTM jako ground (class 2), DSM jako class 1 — stejnou cestou jako ostatní
zdroje, takže pipeline.py nepotřebuje žádnou změnu.
"""

import math
import os
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import requests
from pyproj import CRS, Transformer

from .cancellation import DownloadCancelled

PIXEL_M = 1.0
BUFFER_M = 50.0             # okraj kvůli interpolaci na hraně mapy
MAX_AREA_KM2 = 25.0         # DOM Bavorska ~50 MB/km² → víc už je moc stahování
DOWNLOAD_WORKERS = 4
TIMEOUT_S = 120
_HEADERS = {"User-Agent": "OMapMaker (orienteering map generator)"}

_SN_APP_JSON = ("https://geoviewer.sachsen.de/mapviewer/resources/apps/"
                "produktdownload/app.json")
_SN_DAV = "https://geocloud.landesvermessung.sachsen.de/public.php/dav/files/"

# Hrubé obálky států ve WGS84 (lon_min, lat_min, lon_max, lat_max) — jen aby se
# zbytečně nezkoušely stovky dlaždic státu, který s bboxem nemá nic společného.
# Dlaždice mimo stát prostě vrátí 404 a přeskočí se.
SOURCES = {
    "BY": {
        "name": "Bavorsko (LDBV)",
        "epsg": 25832,
        "tile_km": 1,
        "zipped": False,
        "envelope": (8.95, 47.25, 13.86, 50.58),
        "attribution": "Datenquelle: Bayerische Vermessungsverwaltung – www.geodaten.bayern.de (CC BY 4.0)",
        "dtm": lambda e, n: f"https://download1.bayernwolke.de/a/dgm/dgm1/{e}_{n}.tif",
        "dsm": lambda e, n: f"https://download1.bayernwolke.de/a/dom20/DOM/32{e}_{n}_20_DOM.tif",
    },
    "SN": {
        "name": "Sasko (GeoSN)",
        "epsg": 25833,
        "tile_km": 2,
        "zipped": True,
        "envelope": (11.85, 50.15, 15.06, 51.70),
        "attribution": "Quelle: GeoSN, dl-de/by-2-0",
        "tokens": {"dtm": "JCcXyifaNdLDnxZ", "dsm": "S6wwnFwX7882sZm"},
        "names": {"dtm": "dgm1", "dsm": "dom1"},
    },
}


def _sn_url(kind, token, e, n):
    prod = SOURCES["SN"]["names"][kind]
    return f"{_SN_DAV}{token}/{prod}_33{e}_{n}_2_sn_tiff.zip"


def _url(state, kind, e, n):
    src = SOURCES[state]
    if state == "SN":
        return _sn_url(kind, src["tokens"][kind], e, n)
    return src[kind](e, n)


# ---------------------------------------------------------------------------
# Geometrie
# ---------------------------------------------------------------------------

def _target_epsg(bbox):
    lon_c = (bbox["min_lon"] + bbox["max_lon"]) / 2
    return 25833 if lon_c >= 12.0 else 25832


def _bounds_in(epsg, bbox, buffer_m=0.0):
    """bbox WGS84 → (minx, miny, maxx, maxy) v EPSG s hustě převzorkovanými hranami."""
    t = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    minx, miny, maxx, maxy = t.transform_bounds(
        bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"], densify_pts=21)
    return minx - buffer_m, miny - buffer_m, maxx + buffer_m, maxy + buffer_m


def _envelope_hits(state, bbox):
    lo0, la0, lo1, la1 = SOURCES[state]["envelope"]
    return not (bbox["max_lon"] < lo0 or bbox["min_lon"] > lo1 or
                bbox["max_lat"] < la0 or bbox["min_lat"] > la1)


def _tiles(state, bbox):
    """Seznam (e_km, n_km) levých dolních rohů dlaždic, které protínají bbox."""
    src = SOURCES[state]
    k = src["tile_km"]
    minx, miny, maxx, maxy = _bounds_in(src["epsg"], bbox, BUFFER_M)
    e0 = int(math.floor(minx / 1000 / k)) * k
    n0 = int(math.floor(miny / 1000 / k)) * k
    e1 = int(math.floor(maxx / 1000 / k)) * k
    n1 = int(math.floor(maxy / 1000 / k)) * k
    return [(e, n) for n in range(n0, n1 + 1, k) for e in range(e0, e1 + 1, k)]


# ---------------------------------------------------------------------------
# Stahování
# ---------------------------------------------------------------------------

def _looks_valid(head: bytes, zipped: bool) -> bool:
    # Některé servery vrací na neexistující dlaždici HTTP 200 s HTML stránkou.
    if zipped:
        return head[:2] == b"PK"
    return head[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


def _download(url, dest, zipped, cancel_check=None):
    """Stáhne soubor. Vrací dest, nebo None pokud dlaždice neexistuje."""
    try:
        with requests.get(url, headers=_HEADERS, timeout=TIMEOUT_S, stream=True) as r:
            if r.status_code in (401, 403, 404, 410):
                return None
            r.raise_for_status()
            it = r.iter_content(chunk_size=1 << 20)
            first = next(it, b"")
            if not _looks_valid(first, zipped):
                return None
            with open(dest, "wb") as f:
                f.write(first)
                for chunk in it:
                    if cancel_check and cancel_check():
                        raise DownloadCancelled()
                    f.write(chunk)
        return dest
    except DownloadCancelled:
        if os.path.exists(dest):
            os.remove(dest)
        raise
    except Exception as e:
        if os.path.exists(dest):
            os.remove(dest)
        print(f"[de_downloader] {url}: {e}")
        return None


def _raster_path(path, zipped):
    """Cesta pro rasterio — u ZIPu /vsizip/ na první GeoTIFF uvnitř."""
    if not zipped:
        return path
    with zipfile.ZipFile(path) as z:
        members = sorted(m for m in z.namelist() if m.lower().endswith((".tif", ".tiff")))
    if not members:
        raise ValueError(f"V archivu {os.path.basename(path)} není GeoTIFF")
    return f"/vsizip/{path}/{members[0]}"


def _refresh_sn_tokens(kind, sample_tile, tmp_dir, cb):
    """Zkusí najít platný token sdílení GeoSN v konfiguraci jejich prohlížeče."""
    try:
        r = requests.get(_SN_APP_JSON, headers=_HEADERS, timeout=30)
        r.raise_for_status()
        text = r.text
    except Exception as e:
        cb(f"Sasko: konfiguraci prohlížeče nelze načíst ({e})")
        return False
    cands = []
    for m in re.finditer(r"(?:public\.php/(?:dav/files|webdav)|/s)/([A-Za-z0-9]{10,24})", text):
        if m.group(1) not in cands:
            cands.append(m.group(1))
    old = SOURCES["SN"]["tokens"][kind]
    e, n = sample_tile
    for tok in cands[:40]:
        if tok == old:
            continue
        dest = os.path.join(tmp_dir, f"sn_probe_{kind}.zip")
        if _download(_sn_url(kind, tok, e, n), dest, True):
            os.remove(dest)
            SOURCES["SN"]["tokens"][kind] = tok
            cb(f"Sasko: nalezen nový token pro {SOURCES['SN']['names'][kind]}")
            return True
    return False


# ---------------------------------------------------------------------------
# Mozaika
# ---------------------------------------------------------------------------

class _Grid:
    def __init__(self, epsg, bbox):
        from rasterio.transform import from_origin
        minx, miny, maxx, maxy = _bounds_in(epsg, bbox, BUFFER_M)
        px = PIXEL_M
        self.x0 = math.floor(minx / px) * px
        self.y1 = math.ceil(maxy / px) * px
        self.W = int(math.ceil((maxx - self.x0) / px))
        self.H = int(math.ceil((self.y1 - miny) / px))
        self.epsg = epsg
        self.transform = from_origin(self.x0, self.y1, px, px)

    def empty(self):
        return np.full((self.H, self.W), np.nan, dtype=np.float32)


def _paste(raster_path, grid, mosaic, resampling):
    """Přeprojektuje jednu dlaždici do okna mřížky a doplní jen díry v mozaice."""
    import rasterio
    from rasterio.warp import reproject, transform_bounds
    from rasterio.windows import from_bounds

    with rasterio.open(raster_path) as src:
        src_crs = src.crs or CRS.from_epsg(grid.epsg)
        l, b, r, t = transform_bounds(src_crs, f"EPSG:{grid.epsg}", *src.bounds, densify_pts=21)
        win = from_bounds(l, b, r, t, transform=grid.transform)
        c0 = max(0, int(math.floor(win.col_off)) - 1)
        r0 = max(0, int(math.floor(win.row_off)) - 1)
        c1 = min(grid.W, int(math.ceil(win.col_off + win.width)) + 1)
        r1 = min(grid.H, int(math.ceil(win.row_off + win.height)) + 1)
        if c1 <= c0 or r1 <= r0:
            return 0
        part = np.full((r1 - r0, c1 - c0), np.nan, dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1),
            destination=part,
            src_crs=src_crs,
            src_nodata=src.nodata,
            dst_transform=grid.transform * grid.transform.translation(c0, r0),
            dst_crs=f"EPSG:{grid.epsg}",
            dst_nodata=np.nan,
            resampling=resampling,
        )
    part[(part < -500) | (part > 9000)] = np.nan
    view = mosaic[r0:r1, c0:c1]
    fill = np.isnan(view) & np.isfinite(part)
    view[fill] = part[fill]
    return int(fill.sum())


def _fetch_kind(kind, bbox, states, grid, tmp_dir, cb, cancel_check):
    """Stáhne a složí DTM nebo DSM ze všech relevantních států."""
    from rasterio.enums import Resampling
    # DOM Bavorska má 20 cm — při převzorkování na 1 m bereme maximum, aby
    # koruny stromů a hrany budov nezmizely průměrováním se zemí.
    resampling = Resampling.max if kind == "dsm" else Resampling.bilinear
    label = "DMR" if kind == "dtm" else "DMP"
    mosaic = grid.empty()

    for state in states:
        src = SOURCES[state]
        tiles = _tiles(state, bbox)

        def run(tiles_):
            jobs, got = [], 0
            with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
                for e, n in tiles_:
                    ext = "zip" if src["zipped"] else "tif"
                    dest = os.path.join(tmp_dir, f"{state}_{kind}_{e}_{n}.{ext}")
                    jobs.append(pool.submit(_download, _url(state, kind, e, n), dest,
                                            src["zipped"], cancel_check))
                done = 0
                for fut in as_completed(jobs):
                    path = fut.result()          # DownloadCancelled projde ven
                    done += 1
                    if path is None:
                        continue
                    try:
                        _paste(_raster_path(path, src["zipped"]), grid, mosaic, resampling)
                        got += 1
                    except Exception as ex:
                        cb(f"{src['name']}: dlaždici {os.path.basename(path)} nelze načíst ({ex})")
                    finally:
                        os.remove(path)
                    cb(f"{label} {src['name']}: {done}/{len(tiles_)} dlaždic")
            return got

        cb(f"{label} {src['name']}: stahuji {len(tiles)} dlaždic...")
        got = run(tiles)
        if got == 0 and state == "SN" and tiles:
            # Buď bbox v Sasku vůbec není, nebo GeoSN vyměnil token sdílení.
            if _refresh_sn_tokens(kind, tiles[len(tiles) // 2], tmp_dir, cb):
                got = run(tiles)
        if got:
            cb(f"{label} {src['name']}: {got} dlaždic")
        if cancel_check and cancel_check():
            raise DownloadCancelled()

    return mosaic


# ---------------------------------------------------------------------------
# Zápis LAZ
# ---------------------------------------------------------------------------

def _grid_to_laz(arr, grid, out_path, classification, cb):
    """Mozaiku zapíše jako LAZ po řádkových blocích (nedrží celé x/y/z v paměti)."""
    import laspy

    valid = np.isfinite(arr)
    n_total = int(valid.sum())
    if n_total == 0:
        return False

    header = laspy.LasHeader(point_format=0, version="1.2")
    header.scales = np.array([0.01, 0.01, 0.01])
    header.offsets = np.array([grid.x0, grid.y1 - grid.H * PIXEL_M, float(np.nanmin(arr))])
    header.add_crs(CRS.from_epsg(grid.epsg))

    px = PIXEL_M
    block = max(1, 2_000_000 // max(1, grid.W))
    with laspy.open(out_path, mode="w", header=header) as w:
        for r0 in range(0, grid.H, block):
            sub = arr[r0:r0 + block]
            rows, cols = np.nonzero(np.isfinite(sub))
            if rows.size == 0:
                continue
            pts = laspy.ScaleAwarePointRecord.zeros(rows.size, header=header)
            pts.x = grid.x0 + (cols + 0.5) * px
            pts.y = grid.y1 - (r0 + rows + 0.5) * px
            pts.z = sub[rows, cols].astype(np.float64)
            pts.classification = np.full(rows.size, classification, dtype=np.uint8)
            w.write_points(pts)
    cb(f"Zapsáno {n_total:,} bodů → {os.path.basename(out_path)}")
    return True


# ---------------------------------------------------------------------------
# Hlavní funkce
# ---------------------------------------------------------------------------

def download_germany(bbox: dict, out_dir: str, progress_cb=None, cancel_check=None) -> dict:
    """
    bbox: { min_lat, min_lon, max_lat, max_lon } (WGS84)
    Vrací: { dmr_path, dmp_path, crs }
    """
    os.makedirs(out_dir, exist_ok=True)

    def cb(msg):
        print(f"[de_downloader] {msg}")
        if progress_cb:
            progress_cb(msg)

    def check_cancel():
        if cancel_check and cancel_check():
            raise DownloadCancelled()

    states = [s for s in SOURCES if _envelope_hits(s, bbox)]
    if not states:
        raise RuntimeError("Vybraná oblast není v Bavorsku ani v Sasku.")

    epsg = _target_epsg(bbox)
    grid = _Grid(epsg, bbox)
    area_km2 = grid.W * grid.H * PIXEL_M ** 2 / 1e6
    if area_km2 > MAX_AREA_KM2:
        raise RuntimeError(f"Oblast {area_km2:.1f} km² je moc velká (max {MAX_AREA_KM2:.0f} km²).")
    cb(f"Německo: {', '.join(SOURCES[s]['name'] for s in states)} → EPSG:{epsg}, "
       f"mřížka {grid.W}×{grid.H} m")

    tmp_dir = os.path.join(out_dir, "tiles")
    os.makedirs(tmp_dir, exist_ok=True)

    dtm = _fetch_kind("dtm", bbox, states, grid, tmp_dir, cb, cancel_check)
    check_cancel()
    coverage = float(np.isfinite(dtm).mean())
    if coverage == 0:
        raise RuntimeError("Pro oblast nepřišla žádná DMR dlaždice (mimo pokrytí, nebo je zdroj nedostupný).")
    if coverage < 0.98:
        cb(f"Varování: DMR pokrývá jen {coverage:.0%} oblasti (část bboxu je mimo Bavorsko/Sasko)")

    dmr_path = os.path.join(out_dir, "DE_DGM1_merged.laz")
    _grid_to_laz(dtm, grid, dmr_path, classification=2, cb=cb)
    del dtm
    check_cancel()

    dmp_path = ""
    try:
        dsm = _fetch_kind("dsm", bbox, states, grid, tmp_dir, cb, cancel_check)
        if np.isfinite(dsm).any():
            dmp_path = os.path.join(out_dir, "DE_DOM_merged.laz")
            _grid_to_laz(dsm, grid, dmp_path, classification=1, cb=cb)
        else:
            cb("DMP se nepodařilo stáhnout — mapa bude bez vegetace.")
        del dsm
    except DownloadCancelled:
        raise
    except Exception as e:
        cb(f"Varování DMP: {e} — pokračuji bez vegetace")
        dmp_path = ""

    try:
        os.rmdir(tmp_dir)
    except OSError:
        pass

    cb("Zdroj: " + " | ".join(SOURCES[s]["attribution"] for s in states))
    return {"dmr_path": dmr_path, "dmp_path": dmp_path, "crs": f"EPSG:{epsg}"}
