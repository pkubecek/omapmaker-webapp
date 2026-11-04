"""
core/raster_sources.py — výškopis (DMR + DMP) z rastrových zdrojů mimo ČR/PL/IT.

Každý zdroj umí jednu věc: doplnit do společné 1m mřížky (v CRS výsledku)
výšky tam, kde ještě nic není. Pořadí zdrojů = priorita. Výsledná mozaika
se zapíše jako LAZ (DMR jako ground class 2, DMP class 1), takže pipeline.py
ji zpracuje stejně jako LiDAR z ČÚZK nebo GUGiK.

Zdroje (klíče odpovídají features v coverage.geojson):

  de-XX     Německo, všech 16 spolkových zemí — knihovna geokachel (MIT),
            která zná dlaždice / WCS / archivy každé země zvlášť.
            Šlesvicko-Holštýnsko nepublikuje DOM → jen DMR.
  ch        Švýcarsko + Lichtenštejnsko — swisstopo STAC API,
            swissALTI3D (DMR 0,5 m) a swissSURFACE3D Raster (DMP 0,5 m), COG.
  fr        Francie — IGN Géoplateforme WMS-R, LiDAR HD MNT/MNS (0,5 m),
            DMR doplněn z RGE ALTI 1 m tam, kde LiDAR HD ještě není.
  nl        Nizozemsko — AHN, listy COG na PDOK (DTM/DSM 0,5 m).
  at-tirol  Tyrolsko — ArcGIS WCS tiris (EXPERIMENTÁLNÍ, neověřeno).
  at-stmk   Štýrsko — ArcGIS WCS GIS Steiermark 1 m (EXPERIMENTÁLNÍ).
"""

import json
import math
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import requests
from pyproj import CRS, Transformer

from .cancellation import DownloadCancelled

PIXEL_M = 1.0
BUFFER_M = 50.0
MAX_AREA_KM2 = 25.0
TIMEOUT_S = 120
USER_AGENT = "OMapMaker (+https://www.omapmaker.cz)"
_HEADERS = {"User-Agent": USER_AGENT}

GDAL_ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff",
    GDAL_HTTP_USERAGENT=USER_AGENT,
    GDAL_HTTP_MAX_RETRY="3",
    GDAL_HTTP_RETRY_DELAY="2",
    VSI_CACHE="TRUE",
)


# ---------------------------------------------------------------------------
# Mřížka a vkládání rastrů
# ---------------------------------------------------------------------------

def bbox_bounds(epsg, bbox, buffer_m=0.0):
    """bbox WGS84 {min_lat,...} → (minx, miny, maxx, maxy) v EPSG."""
    t = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    minx, miny, maxx, maxy = t.transform_bounds(
        bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"], densify_pts=21)
    return minx - buffer_m, miny - buffer_m, maxx + buffer_m, maxy + buffer_m


class Grid:
    """Cílová 1m mřížka v CRS výsledku."""

    def __init__(self, epsg, bbox):
        from rasterio.transform import from_origin
        minx, miny, maxx, maxy = bbox_bounds(epsg, bbox, BUFFER_M)
        px = PIXEL_M
        self.epsg = epsg
        self.x0 = math.floor(minx / px) * px
        self.y1 = math.ceil(maxy / px) * px
        self.W = int(math.ceil((maxx - self.x0) / px))
        self.H = int(math.ceil((self.y1 - miny) / px))
        self.transform = from_origin(self.x0, self.y1, px, px)

    @property
    def bounds(self):
        return self.x0, self.y1 - self.H * PIXEL_M, self.x0 + self.W * PIXEL_M, self.y1

    @property
    def area_km2(self):
        return self.W * self.H * PIXEL_M ** 2 / 1e6

    def empty(self):
        return np.full((self.H, self.W), np.nan, dtype=np.float32)

    def bounds_in(self, epsg):
        from rasterio.warp import transform_bounds
        if epsg == self.epsg:
            return self.bounds
        return transform_bounds(f"EPSG:{self.epsg}", f"EPSG:{epsg}", *self.bounds, densify_pts=21)


def _window_for(grid, src_crs, src_bounds):
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds
    l, b, r, t = transform_bounds(src_crs, f"EPSG:{grid.epsg}", *src_bounds, densify_pts=21)
    win = from_bounds(l, b, r, t, transform=grid.transform)
    c0 = max(0, int(math.floor(win.col_off)) - 1)
    r0 = max(0, int(math.floor(win.row_off)) - 1)
    c1 = min(grid.W, int(math.ceil(win.col_off + win.width)) + 1)
    r1 = min(grid.H, int(math.ceil(win.row_off + win.height)) + 1)
    if c1 <= c0 or r1 <= r0:
        return None
    return r0, r1, c0, c1


def _merge_part(mosaic, part, r0, c0):
    part[(part < -500) | (part > 9000)] = np.nan
    view = mosaic[r0:r0 + part.shape[0], c0:c0 + part.shape[1]]
    fill = np.isnan(view) & np.isfinite(part)
    view[fill] = part[fill]
    return int(fill.sum())


def paste_dataset(ds, grid, mosaic, resampling, src_crs=None, nodata=None):
    """Přeprojektuje otevřený rasterio dataset do mozaiky (jen do děr)."""
    import rasterio
    from rasterio.warp import reproject
    crs = src_crs or ds.crs
    w = _window_for(grid, crs, ds.bounds)
    if w is None:
        return 0
    r0, r1, c0, c1 = w
    part = np.full((r1 - r0, c1 - c0), np.nan, dtype=np.float32)
    reproject(
        source=rasterio.band(ds, 1), destination=part,
        src_crs=crs, src_nodata=nodata if nodata is not None else ds.nodata,
        dst_transform=grid.transform * grid.transform.translation(c0, r0),
        dst_crs=f"EPSG:{grid.epsg}", dst_nodata=np.nan, resampling=resampling,
    )
    return _merge_part(mosaic, part, r0, c0)


def paste_array(arr, transform, epsg, grid, mosaic, resampling, nodata=None):
    """Totéž pro numpy pole se známou georeferencí."""
    from rasterio.transform import array_bounds
    from rasterio.warp import reproject
    arr = arr.astype(np.float32, copy=False)
    if nodata is not None:
        arr = np.where(arr == nodata, np.nan, arr)
    h, w_ = arr.shape
    west, south, east, north = array_bounds(h, w_, transform)
    w = _window_for(grid, f"EPSG:{epsg}", (west, south, east, north))
    if w is None:
        return 0
    r0, r1, c0, c1 = w
    part = np.full((r1 - r0, c1 - c0), np.nan, dtype=np.float32)
    reproject(
        source=arr, destination=part, src_transform=transform, src_crs=f"EPSG:{epsg}",
        src_nodata=np.nan, dst_transform=grid.transform * grid.transform.translation(c0, r0),
        dst_crs=f"EPSG:{grid.epsg}", dst_nodata=np.nan, resampling=resampling,
    )
    return _merge_part(mosaic, part, r0, c0)


def open_remote(url):
    """COG přes HTTP (range requesty GDAL). Lokální cesta se otevře přímo."""
    import rasterio
    return rasterio.open(url if os.path.exists(url) else f"/vsicurl/{url}")


def _resampling(kind):
    from rasterio.enums import Resampling
    # DMP z jemnějšího rastru → maximum, aby koruny a hrany budov nezmizely.
    return Resampling.max if kind == "dsm" else Resampling.bilinear


def _get(url, **kw):
    r = requests.get(url, headers=_HEADERS, timeout=kw.pop("timeout", TIMEOUT_S), **kw)
    r.raise_for_status()
    return r


class Ctx:
    """Co zdroj potřebuje: mřížku, mozaiky, dočasný adresář, callbacky."""

    def __init__(self, grid, bbox, tmp_dir, cb, cancel_check):
        self.grid = grid
        self.bbox = bbox
        self.tmp_dir = tmp_dir
        self.cb = cb
        self.cancel_check = cancel_check
        self.dtm = grid.empty()
        self.dsm = grid.empty()
        # DMP publikovaný relativně k terénu (nDOM) — přičte se DMR na konci
        self.ndsm = grid.empty()

    def mosaic(self, kind):
        return self.dtm if kind == "dtm" else self.dsm

    def check(self):
        if self.cancel_check and self.cancel_check():
            raise DownloadCancelled()


# ---------------------------------------------------------------------------
# Německo — geokachel
# ---------------------------------------------------------------------------

DE_WINDOW_M = 900.0   # Bavorský DOM má 20 cm a geokachel bere max 25 Mpx na okno


def _de_state_epsg(state):
    from geokachel.tile_terms import TERMS
    return TERMS[state][2]


class GermanyState:
    def __init__(self, state, geom):
        self.key = f"de-{state}"
        self.state = state
        self.geom = geom          # shapely polygon WGS84 (z coverage.geojson)
        self.name = f"Německo ({state})"

    @property
    def native_epsg(self):
        return _de_state_epsg(self.state)

    @property
    def attribution(self):
        from geokachel.tile_terms import TERMS
        return TERMS[self.state][1]

    def _windows(self, ctx):
        """Středy oken (lat, lon) v pravidelné síti UTM, jen ta blízko území země."""
        from shapely.geometry import Point
        epsg = self.native_epsg
        minx, miny, maxx, maxy = ctx.grid.bounds_in(epsg)
        s = DE_WINDOW_M
        to_ll = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
        near = self.geom.buffer(0.02)          # ~2 km tolerance hranice z Natural Earth
        out = []
        y = math.floor(miny / s) * s
        while y < maxy:
            x = math.floor(minx / s) * s
            while x < maxx:
                lon, lat = to_ll.transform(x + s / 2, y + s / 2)
                if near.contains(Point(lon, lat)):
                    out.append((lat, lon))
                x += s
            y += s
        return out

    def fetch(self, kind, ctx):
        import geokachel
        from geokachel import net as gk_net
        from geokachel.tile_cache import TileCache
        from geokachel.window import GROUND
        gk_net.USER_AGENT = USER_AGENT
        cache_dir = Path(ctx.tmp_dir) / "geokachel"
        cache = TileCache(cache_dir, 6_000_000_000)
        fn = geokachel.ground if kind == "dtm" else geokachel.surface
        wins = self._windows(ctx)
        got, errors = 0, []
        for i, (lat, lon) in enumerate(wins, 1):
            ctx.check()
            try:
                w = fn(lat, lon, state=self.state, size_m=DE_WINDOW_M + 60, cache=cache)
            except Exception as e:          # Unavailable, FetchError, ValueError...
                errors.append(str(e))
                continue
            from rasterio.transform import from_origin
            tr = from_origin(w.west, w.north, w.cell_m, w.cell_m)
            target = ctx.ndsm if (kind == "dsm" and w.heights_above == GROUND) else ctx.mosaic(kind)
            if paste_array(np.asarray(w.values, dtype=np.float32), tr, w.epsg, ctx.grid,
                           target, _resampling(kind)):
                got += 1
            if i % 3 == 0 or i == len(wins):
                ctx.cb(f"{'DMR' if kind == 'dtm' else 'DMP'} {self.name}: {i}/{len(wins)}")
        if not got and errors:
            ctx.cb(f"{self.name}: {errors[0][:160]}")
        return got


# ---------------------------------------------------------------------------
# Švýcarsko — swisstopo STAC
# ---------------------------------------------------------------------------

_CH_STAC = "https://data.geo.admin.ch/api/stac/v1/collections/{coll}/items"
_CH_COLL = {"dtm": "ch.swisstopo.swissalti3d", "dsm": "ch.swisstopo.swisssurface3d-raster"}
_CH_TILE_RE = re.compile(r"_(\d{4})_(\d{4}-\d{4})")


class Switzerland:
    key = "ch"
    name = "Švýcarsko (swisstopo)"
    native_epsg = 2056
    attribution = "© swisstopo"

    def _assets(self, kind, ctx):
        b = ctx.bbox
        url = _CH_STAC.format(coll=_CH_COLL[kind])
        params = {"bbox": f"{b['min_lon']},{b['min_lat']},{b['max_lon']},{b['max_lat']}", "limit": 100}
        latest = {}                    # tile → (year, href)
        pages = 0
        while url and pages < 20:
            data = _get(url, params=params, timeout=60).json()
            params = None              # další stránky mají parametry v odkazu
            pages += 1
            for item in data.get("features", []):
                m = _CH_TILE_RE.search(item.get("id", ""))
                if not m:
                    continue
                year, tile = int(m.group(1)), m.group(2)
                tifs = [(k, a) for k, a in item.get("assets", {}).items() if k.endswith(".tif")]
                # nejjemnější rozlišení (0.5 m), jinak cokoli
                tifs.sort(key=lambda ka: float(ka[1].get("eo:gsd") or ka[1].get("gsd") or 99))
                if tifs and (tile not in latest or year > latest[tile][0]):
                    latest[tile] = (year, tifs[0][1]["href"])
            url = next((l["href"] for l in data.get("links", []) if l.get("rel") == "next"), None)
        return [h for _, h in latest.values()]

    def fetch(self, kind, ctx):
        import rasterio
        hrefs = self._assets(kind, ctx)
        got = 0
        with rasterio.Env(**GDAL_ENV):
            for i, href in enumerate(hrefs, 1):
                ctx.check()
                try:
                    with open_remote(href) as ds:
                        if paste_dataset(ds, ctx.grid, ctx.mosaic(kind), _resampling(kind)):
                            got += 1
                except Exception as e:
                    ctx.cb(f"{self.name}: {os.path.basename(href)} nelze načíst ({e})")
                ctx.cb(f"{'DMR' if kind == 'dtm' else 'DMP'} {self.name}: {i}/{len(hrefs)}")
        return got


# ---------------------------------------------------------------------------
# Francie — IGN Géoplateforme WMS-R (raw Float32 GeoTIFF)
# ---------------------------------------------------------------------------

_FR_WMS = "https://data.geopf.fr/wms-r/wms"
_FR_LAYERS = {
    "dtm": ["IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93",
            "ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES"],          # RGE ALTI 1 m jako záloha
    "dsm": ["IGNF_LIDAR-HD_MNS_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93"],
}
_FR_MAX_PX = 4000


class France:
    key = "fr"
    name = "Francie (IGN)"
    native_epsg = 2154
    attribution = "© IGN – LiDAR HD / RGE ALTI, Licence Ouverte 2.0"

    def _getmap(self, layer, bbox, w, h):
        params = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": layer,
                  "STYLES": "", "CRS": "EPSG:2154", "BBOX": "%.2f,%.2f,%.2f,%.2f" % bbox,
                  "WIDTH": str(w), "HEIGHT": str(h), "FORMAT": "image/tiff"}
        r = requests.get(_FR_WMS, params=params, headers=_HEADERS, timeout=TIMEOUT_S)
        data = r.content
        if r.status_code != 200 or data[:4] not in (b"II*\x00", b"MM\x00*"):
            raise RuntimeError(f"WMS-R {layer}: HTTP {r.status_code} {data[:200]!r}")
        from rasterio.io import MemoryFile
        with MemoryFile(data) as mf, mf.open() as ds:
            arr = ds.read(1).astype(np.float32)
        arr[(arr <= -9999) | (arr < -500)] = np.nan
        return arr

    def fetch(self, kind, ctx):
        from rasterio.transform import from_bounds
        minx, miny, maxx, maxy = ctx.grid.bounds_in(2154)
        px = 1.0
        minx, miny = math.floor(minx), math.floor(miny)
        maxx, maxy = math.ceil(maxx), math.ceil(maxy)
        step = _FR_MAX_PX * px
        got = 0
        for layer in _FR_LAYERS[kind]:
            for y in np.arange(miny, maxy, step):
                for x in np.arange(minx, maxx, step):
                    ctx.check()
                    x1, y1 = min(x + step, maxx), min(y + step, maxy)
                    w, h = int(round((x1 - x) / px)), int(round((y1 - y) / px))
                    try:
                        arr = self._getmap(layer, (x, y, x1, y1), w, h)
                    except Exception as e:
                        ctx.cb(f"{self.name}: {e}"[:200])
                        continue
                    tr = from_bounds(x, y, x1, y1, w, h)
                    if paste_array(arr, tr, 2154, ctx.grid, ctx.mosaic(kind), _resampling(kind)):
                        got += 1
            ctx.cb(f"{'DMR' if kind == 'dtm' else 'DMP'} {self.name}: {layer.split('_')[0]} hotovo")
        return got


# ---------------------------------------------------------------------------
# Nizozemsko — AHN (PDOK, listy COG + index)
# ---------------------------------------------------------------------------

_NL_INDEX = ("https://service.pdok.nl/rws/actueel-hoogtebestand-nederland/atom/downloads/"
             "{prod}/kaartbladindex.json")
_NL_PROD = {"dtm": "dtm_05m", "dsm": "dsm_05m"}
_NL_INDEX_CACHE = {}


def _coords_bounds(geom):
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for cc in c:
                walk(cc)
    walk(geom["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


class Netherlands:
    key = "nl"
    name = "Nizozemsko (AHN)"
    native_epsg = 28992
    attribution = "© AHN / Rijkswaterstaat (CC0)"

    def _index(self, kind):
        prod = _NL_PROD[kind]
        if prod not in _NL_INDEX_CACHE:
            data = _get(_NL_INDEX.format(prod=prod), timeout=60).json()
            sheets = []
            for f in data.get("features", []):
                p = f.get("properties", {})
                url = p.get("url")
                if not url and p.get("name"):
                    url = _NL_INDEX.format(prod=prod).rsplit("/", 1)[0] + "/" + p["name"]
                if url and f.get("geometry"):
                    sheets.append((_coords_bounds(f["geometry"]), url))
            _NL_INDEX_CACHE[prod] = sheets
        return _NL_INDEX_CACHE[prod]

    def fetch(self, kind, ctx):
        import rasterio
        minx, miny, maxx, maxy = ctx.grid.bounds_in(28992)
        sheets = [u for (x0, y0, x1, y1), u in self._index(kind)
                  if not (x1 < minx or x0 > maxx or y1 < miny or y0 > maxy)]
        got = 0
        with rasterio.Env(**GDAL_ENV):
            for i, url in enumerate(sheets, 1):
                ctx.check()
                try:
                    with open_remote(url) as ds:
                        if paste_dataset(ds, ctx.grid, ctx.mosaic(kind), _resampling(kind),
                                         src_crs=ds.crs or "EPSG:28992"):
                            got += 1
                except Exception as e:
                    ctx.cb(f"{self.name}: {os.path.basename(url)} nelze načíst ({e})")
                ctx.cb(f"{'DMR' if kind == 'dtm' else 'DMP'} {self.name}: list {i}/{len(sheets)}")
        return got


# ---------------------------------------------------------------------------
# Rakousko — ArcGIS WCS spolkových zemí (EXPERIMENTÁLNÍ)
# ---------------------------------------------------------------------------

_SKIP_WORDS = ("neigung", "schummer", "hillshade", "exposition", "höhenschicht",
               "hoehenschicht", "kontur", "contour", "slope", "aspect", "wintersport")


class AustriaWCS:
    """ArcGIS MapServer WCS 1.0.0. Id coverage se hledá v GetCapabilities podle
    názvu (DGM/Gelände vs. DOM/Oberfläche) — služby ID nedokumentují."""

    def __init__(self, key, name, urls, attribution):
        self.key = key
        self.name = name
        self.urls = urls              # {"dtm": url, "dsm": url}
        self.attribution = attribution
        self._cov = {}

    native_epsg = None                # určí se podle polohy (UTM 32/33)

    def _coverage(self, kind):
        url = self.urls[kind]
        if (url, kind) in self._cov:
            return self._cov[(url, kind)]
        xml = _get(url, params={"SERVICE": "WCS", "VERSION": "1.0.0",
                                "REQUEST": "GetCapabilities"}, timeout=60).text
        root = ET.fromstring(xml.encode("utf-8"))
        best = None
        for el in root.iter():
            if not el.tag.endswith("CoverageOfferingBrief"):
                continue
            name = next((c.text for c in el if c.tag.endswith("name")), None)
            label = " ".join((c.text or "") for c in el if c.tag.endswith(("label", "description"))).lower()
            if not name or any(w in label for w in _SKIP_WORDS):
                continue
            want = ("dgm", "gelände", "gelaende", "terrain") if kind == "dtm" else \
                   ("dom", "oberfläche", "oberflaeche", "surface")
            score = sum(w in label for w in want)
            if self.urls["dtm"] != self.urls["dsm"] and score == 0:
                score = 0.5          # samostatná služba jen s jedním produktem
            if score and (best is None or score > best[0]):
                best = (score, name)
        if best is None:
            raise RuntimeError(f"{self.name}: v GetCapabilities není {'DGM' if kind == 'dtm' else 'DOM'}")
        self._cov[(url, kind)] = best[1]
        return best[1]

    def fetch(self, kind, ctx):
        from rasterio.io import MemoryFile
        cov = self._coverage(kind)
        minx, miny, maxx, maxy = ctx.grid.bounds
        step = 4000.0
        got = 0
        for y in np.arange(miny, maxy, step):
            for x in np.arange(minx, maxx, step):
                ctx.check()
                x1, y1 = min(x + step, maxx), min(y + step, maxy)
                params = {"SERVICE": "WCS", "VERSION": "1.0.0", "REQUEST": "GetCoverage",
                          "COVERAGE": cov, "CRS": f"EPSG:{ctx.grid.epsg}",
                          "RESPONSE_CRS": f"EPSG:{ctx.grid.epsg}",
                          "BBOX": f"{x},{y},{x1},{y1}", "WIDTH": int(round(x1 - x)),
                          "HEIGHT": int(round(y1 - y)), "FORMAT": "GeoTIFF"}
                try:
                    r = requests.get(self.urls[kind], params=params, headers=_HEADERS, timeout=TIMEOUT_S)
                    if r.status_code != 200 or r.content[:2] not in (b"II", b"MM"):
                        raise RuntimeError(f"HTTP {r.status_code} {r.content[:200]!r}")
                    with MemoryFile(r.content) as mf, mf.open() as ds:
                        if paste_dataset(ds, ctx.grid, ctx.mosaic(kind), _resampling(kind)):
                            got += 1
                except Exception as e:
                    ctx.cb(f"{self.name}: {e}"[:200])
        ctx.cb(f"{'DMR' if kind == 'dtm' else 'DMP'} {self.name}: {got} výřezů")
        return got


# ---------------------------------------------------------------------------
# Registr
# ---------------------------------------------------------------------------

_COVERAGE_PATH = os.path.join(os.path.dirname(__file__), "coverage.geojson")
_COVERAGE = None


def coverage():
    """[(key, group, label, shapely geom WGS84)] z coverage.geojson."""
    global _COVERAGE
    if _COVERAGE is None:
        from shapely.geometry import shape
        with open(_COVERAGE_PATH, encoding="utf-8") as f:
            fc = json.load(f)
        _COVERAGE = [(ft["properties"]["key"], ft["properties"]["group"],
                      ft["properties"]["label"], shape(ft["geometry"])) for ft in fc["features"]]
    return _COVERAGE


def make_source(key):
    if key.startswith("de-"):
        geom = next(g for k, _, _, g in coverage() if k == key)
        return GermanyState(key[3:], geom)
    if key == "ch":
        return Switzerland()
    if key == "fr":
        return France()
    if key == "nl":
        return Netherlands()
    if key == "at-tirol":
        u = "https://gis.tirol.gv.at/arcgis/services/Service_Public/terrain/MapServer/WCSServer"
        return AustriaWCS(key, "Tyrolsko (tiris)", {"dtm": u, "dsm": u}, "© Land Tirol – data.tirol.gv.at")
    if key == "at-stmk":
        base = "https://gis.stmk.gv.at/arcgis/services/OGD/{}/MapServer/WCSServer"
        return AustriaWCS(key, "Štýrsko (GIS Steiermark)",
                          {"dtm": base.format("ALSGelaendeinformation_1m_UTM33N"),
                           "dsm": base.format("ALSHoeheninformation_1m_UTM33N")},
                          "© Land Steiermark – gis.stmk.gv.at")
    raise KeyError(key)


RASTER_KEYS_PREFIX = ("de-", "ch", "fr", "nl", "at-")


def is_raster_key(key):
    return key.startswith(RASTER_KEYS_PREFIX)


def native_epsg(key, bbox):
    src = make_source(key)
    if src.native_epsg:
        return src.native_epsg
    lon_c = (bbox["min_lon"] + bbox["max_lon"]) / 2
    return 25833 if lon_c >= 12.0 else 25832


# ---------------------------------------------------------------------------
# Zápis LAZ
# ---------------------------------------------------------------------------

def grid_to_laz(arr, grid, out_path, classification, cb=None):
    """Mozaiku zapíše jako LAZ po řádkových blocích."""
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
    if cb:
        cb(f"Zapsáno {n_total:,} bodů → {os.path.basename(out_path)}")
    return True


# ---------------------------------------------------------------------------
# Hlavní funkce
# ---------------------------------------------------------------------------

def download_raster(bbox, out_dir, keys, target_epsg, progress_cb=None, cancel_check=None):
    """
    Stáhne DMR + DMP ze zdrojů `keys` (v pořadí priority) do 1m mřížky
    v `target_epsg` a zapíše LAZ. Vrací {dmr_path, dmp_path, crs, attribution}.
    """
    os.makedirs(out_dir, exist_ok=True)

    def cb(msg):
        print(f"[raster] {msg}")
        if progress_cb:
            progress_cb(msg)

    grid = Grid(target_epsg, bbox)
    if grid.area_km2 > MAX_AREA_KM2:
        raise RuntimeError(f"Oblast {grid.area_km2:.1f} km² je moc velká (max {MAX_AREA_KM2:.0f} km²).")
    sources = [make_source(k) for k in keys]
    cb(f"Zdroje: {', '.join(s.name for s in sources)} → EPSG:{target_epsg}, {grid.W}×{grid.H} m")

    tmp_dir = tempfile.mkdtemp(prefix="tiles_", dir=out_dir)
    ctx = Ctx(grid, bbox, tmp_dir, cb, cancel_check)
    used = []
    try:
        for kind in ("dtm", "dsm"):
            for src in sources:
                ctx.check()
                try:
                    n = src.fetch(kind, ctx)
                except DownloadCancelled:
                    raise
                except Exception as e:
                    cb(f"Varování {src.name} ({'DMR' if kind == 'dtm' else 'DMP'}): {e}"[:240])
                    n = 0
                if n and src not in used:
                    used.append(src)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # nDOM (relativní výšky) → absolutní DMP
    fill = np.isnan(ctx.dsm) & np.isfinite(ctx.ndsm) & np.isfinite(ctx.dtm)
    ctx.dsm[fill] = ctx.dtm[fill] + np.maximum(ctx.ndsm[fill], 0)
    del ctx.ndsm

    cover = float(np.isfinite(ctx.dtm).mean())
    if cover == 0:
        raise RuntimeError("Ze zdrojů nepřišla žádná výšková data (mimo pokrytí, nebo jsou služby nedostupné).")
    if cover < 0.98:
        cb(f"Varování: DMR pokrývá {cover:.0%} oblasti")

    dmr_path = os.path.join(out_dir, "RASTER_DMR_merged.laz")
    grid_to_laz(ctx.dtm, grid, dmr_path, 2, cb)
    dmp_path = ""
    if np.isfinite(ctx.dsm).any():
        dmp_path = os.path.join(out_dir, "RASTER_DMP_merged.laz")
        grid_to_laz(ctx.dsm, grid, dmp_path, 1, cb)
    else:
        cb("DMP není k dispozici — mapa bude bez vegetace.")

    attribution = " | ".join(dict.fromkeys(s.attribution for s in used))
    cb("Zdroj: " + attribution)
    return {"dmr_path": dmr_path, "dmp_path": dmp_path, "crs": f"EPSG:{target_epsg}",
            "attribution": attribution}
