"""
ortho_surface.py — zpevněné plochy (501) a zeleň (401) z ortofota.

Jen pro sprintový klíč (ISSprOM 2019-2, 1:4000), zapíná se checkboxem
v nastavení (params["ortho_surface"]).

Postup:
  1. stažení RGB ortofota z WMS (ČÚZK pro EPSG:5514, GUGiK pro EPSG:2180)
     po dlaždicích max 4000 px, rozlišení ORTHO_PIXEL_M
  2. vegetační index ExG = 2g - r - b na normalizovaných barvách
     (r = R/(R+G+B) ...) — normalizace potlačí vliv jasu/stínů
  3. práh Otsu, oříznutý do rozumného rozsahu (když je ve výřezu
     skoro jen zeleň nebo skoro jen asfalt, Otsu sám ujede)
  4. masky z OSM: budovy a voda se vyřadí úplně, venkovské plochy
     (pole, les, louka...) nesmí být "zpevněné", pod silnicemi se
     zpevněná plocha vynutí (koruny stromů nad ulicí)
  5. morfologické vyčištění, převod na polygony

Výstup: GeoDataFrame se sloupcem class_name ∈ {"Orto_zpevneno", "Orto_zelen"}.
"""
import io
import math

import numpy as np
import pandas as pd
import geopandas as gpd
import requests
from PIL import Image
from pyproj import CRS
from rasterio.features import rasterize, shapes
from rasterio.transform import from_origin
from scipy import ndimage
from shapely.geometry import shape, box

# Rozlišení klasifikace. 0.5 m/px = 0.125 mm na mapě 1:4000 — víc není
# potřeba a proti nativním 0.25 m je to 4× méně dat i paměti.
ORTHO_PIXEL_M = 0.5
MAX_WMS_PX = 4000          # obě služby mají MaxWidth/MaxHeight 4096
MAX_AREA_KM2 = 25.0        # pojistka paměti (25 km² ≈ 100 Mpx při 0.5 m)
WMS_TIMEOUT_S = 60

WMS_SOURCES = {
    5514: {
        "url": "https://ags.cuzk.gov.cz/arcgis1/services/ORTOFOTO/MapServer/WMSServer",
        "layer": "0",
        "name": "ČÚZK",
    },
    2180: {
        "url": "https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution",
        "layer": "Raster",
        "name": "GUGiK",
    },
}

# Minimální plocha ostrůvku / díry (m²). 16 m² = 1 mm² na mapě 1:4000.
MIN_AREA_M2 = 16.0
# Rozsah, do kterého se ořízne Otsu práh ExG (normalizovaný ExG je v <-1, 2>).
EXG_THRESHOLD_MIN = 0.04
EXG_THRESHOLD_MAX = 0.12
# Pixely tmavší než tohle (součet R+G+B) jsou stín → třída se doplní od sousedů.
SHADOW_SUM = 60

# Silnice, pod kterými se zpevněná plocha vynutí, s polovinou šířky v m.
ROAD_HALF_WIDTH = {
    "motorway": 6.0, "trunk": 6.0, "primary": 5.0, "secondary": 4.5,
    "tertiary": 4.0, "unclassified": 3.0, "residential": 3.0,
    "living_street": 3.0, "pedestrian": 2.0, "service": 2.0,
    "motorway_link": 4.0, "trunk_link": 4.0, "primary_link": 4.0,
    "secondary_link": 3.5, "tertiary_link": 3.0,
}
# Plochy, kde zpevněná plocha nedává smysl (holá pole, les, louky...).
RURAL_LANDUSE = {"farmland", "meadow", "orchard", "vineyard", "forest", "grass",
                 "allotments", "plant_nursery", "greenfield", "village_green",
                 "recreation_ground", "cemetery"}
RURAL_NATURAL = {"wood", "scrub", "heath", "grassland", "wetland", "sand",
                 "beach", "bare_rock", "scree", "shingle"}
WATER_NATURAL = {"water", "bay"}
WATER_LANDUSE = {"reservoir", "basin"}


def _wms_get(src, epsg, bbox, width, height):
    """Jeden GetMap. Nejdřív WMS 1.1.1 (pořadí os vždy x,y), při chybě
    1.3.0 s pořadím os podle definice CRS (EPSG:2180 je N,E)."""
    minx, miny, maxx, maxy = bbox
    base = {"SERVICE": "WMS", "REQUEST": "GetMap", "LAYERS": src["layer"],
            "STYLES": "", "FORMAT": "image/jpeg", "WIDTH": width, "HEIGHT": height}
    attempts = [dict(base, VERSION="1.1.1", SRS=f"EPSG:{epsg}",
                     BBOX=f"{minx},{miny},{maxx},{maxy}")]
    axis = CRS.from_epsg(epsg).axis_info
    north_first = bool(axis) and axis[0].direction.lower() == "north"
    bb13 = f"{miny},{minx},{maxy},{maxx}" if north_first else f"{minx},{miny},{maxx},{maxy}"
    attempts.append(dict(base, VERSION="1.3.0", CRS=f"EPSG:{epsg}", BBOX=bb13))

    last_err = None
    for p in attempts:
        try:
            r = requests.get(src["url"], params=p, timeout=WMS_TIMEOUT_S,
                             headers={"User-Agent": "OMapMaker-Web-v7"})
            ctype = r.headers.get("Content-Type", "")
            if r.status_code != 200 or not ctype.startswith("image"):
                last_err = RuntimeError(f"HTTP {r.status_code}, {ctype}: {r.text[:200]!r}")
                continue
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            if img.size != (width, height):
                img = img.resize((width, height), Image.BILINEAR)
            return np.asarray(img, dtype=np.uint8)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"WMS {src['name']} GetMap selhal: {last_err}")


def fetch_ortho(extent, crs, progress_cb=None):
    """Stáhne RGB ortofoto pro extent=(minx, maxx, miny, maxy).
    Vrací (rgb uint8 HxWx3, affine transform) nebo None, když pro CRS
    není zdroj."""
    def cb(m):
        if progress_cb:
            progress_cb(m)

    epsg = CRS.from_user_input(crs).to_epsg()
    src = WMS_SOURCES.get(epsg)
    if src is None:
        cb(f"Ortofoto: pro {crs} není zdroj (jen EPSG:5514 / EPSG:2180), přeskakuji")
        return None

    minx, maxx, miny, maxy = extent
    area_km2 = (maxx - minx) * (maxy - miny) / 1e6
    if area_km2 > MAX_AREA_KM2:
        cb(f"Ortofoto: oblast {area_km2:.1f} km² > {MAX_AREA_KM2} km², přeskakuji")
        return None

    px = ORTHO_PIXEL_M
    W = int(math.ceil((maxx - minx) / px))
    H = int(math.ceil((maxy - miny) / px))
    rgb = np.zeros((H, W, 3), dtype=np.uint8)
    nx = int(math.ceil(W / MAX_WMS_PX))
    ny = int(math.ceil(H / MAX_WMS_PX))
    cb(f"Ortofoto {src['name']}: {W}×{H} px, {nx * ny} požadavků")

    for iy in range(ny):
        for ix in range(nx):
            c0, c1 = ix * MAX_WMS_PX, min(W, (ix + 1) * MAX_WMS_PX)
            r0, r1 = iy * MAX_WMS_PX, min(H, (iy + 1) * MAX_WMS_PX)
            # řádek 0 = sever
            bx0 = minx + c0 * px
            bx1 = minx + c1 * px
            by1 = miny + H * px - r0 * px
            by0 = miny + H * px - r1 * px
            rgb[r0:r1, c0:c1] = _wms_get(src, epsg, (bx0, by0, bx1, by1), c1 - c0, r1 - r0)

    transform = from_origin(minx, miny + H * px, px, px)
    return rgb, transform


def _osm_masks(gdf_osm, out_shape, transform):
    """Rasterové masky z OSM: (vyřadit_vše, venkov, vynutit_zpevněno)."""
    empty = np.zeros(out_shape, dtype=bool)
    if gdf_osm is None or gdf_osm.empty:
        return empty, empty.copy(), empty.copy()

    def col(name):
        if name in gdf_osm.columns:
            # fillna PŘED astype: v pandas 3 astype(str) nechá NaN jako NaN
            # (ne řetězec "nan"), takže porovnání ne("nan") bylo vždy True
            # a každý polygon se bral jako budova → vše vyřazeno
            return gdf_osm[name].fillna("").astype(str)
        return pd.Series("", index=gdf_osm.index)

    gt = gdf_osm.geometry.geom_type
    polys = gt.isin(["Polygon", "MultiPolygon"])
    lines = gt.isin(["LineString", "MultiLineString"])

    def burn(geoms):
        geoms = [g for g in geoms if g is not None and not g.is_empty]
        if not geoms:
            return empty.copy()
        return rasterize(((g, 1) for g in geoms), out_shape=out_shape,
                         transform=transform, fill=0, dtype="uint8").astype(bool)

    building = polys & col("building").ne("") & col("building").ne("roof")
    water = polys & (col("natural").isin(WATER_NATURAL) |
                     col("landuse").isin(WATER_LANDUSE) |
                     col("waterway").isin({"riverbank", "dock"}))
    exclude = burn(gdf_osm.geometry[building | water])

    rural = polys & (col("landuse").isin(RURAL_LANDUSE) | col("natural").isin(RURAL_NATURAL))
    rural_mask = burn(gdf_osm.geometry[rural])

    hw = col("highway")
    road = lines & hw.isin(ROAD_HALF_WIDTH.keys()) & \
        ~col("tunnel").isin({"yes", "building_passage", "culvert"}) & col("covered").ne("yes")
    road_geoms = [g.buffer(ROAD_HALF_WIDTH[h], cap_style=2)
                  for g, h in zip(gdf_osm.geometry[road], hw[road])]
    # pěší zóny / náměstí jako plochy
    plaza = polys & (hw.isin({"pedestrian", "footway"}) | col("area:highway").ne("") |
                     col("place").eq("square") | col("amenity").eq("parking"))
    road_geoms += list(gdf_osm.geometry[plaza])
    force_paved = burn(road_geoms)

    return exclude, rural_mask, force_paved


def classify_surface(rgb, transform, crs, gdf_osm=None, progress_cb=None):
    """RGB → GeoDataFrame zpevněných ploch a zeleně."""
    def cb(m):
        if progress_cb:
            progress_cb(m)

    H, W, _ = rgb.shape
    px = abs(transform.a)

    R = rgb[..., 0].astype(np.float32)
    G = rgb[..., 1].astype(np.float32)
    B = rgb[..., 2].astype(np.float32)
    S = R + G + B
    nodata = (S <= 15) | ((R >= 250) & (G >= 250) & (B >= 250))
    with np.errstate(divide="ignore", invalid="ignore"):
        exg = (2.0 * G - R - B) / np.where(S > 0, S, 1.0)
    del R, G, B

    shadow = (S < SHADOW_SUM) & ~nodata
    decided = ~nodata & ~shadow
    del S

    # Otsu práh na rozhodnutelných pixelech
    try:
        from skimage.filters import threshold_otsu
        sample = exg[decided]
        if sample.size > 2_000_000:
            sample = np.random.default_rng(0).choice(sample, 2_000_000, replace=False)
        thr = float(threshold_otsu(sample)) if sample.size > 100 else 0.08
    except Exception:
        thr = 0.08
    thr = min(max(thr, EXG_THRESHOLD_MIN), EXG_THRESHOLD_MAX)
    cb(f"Ortofoto: práh ExG = {thr:.3f}")

    green = exg > thr
    del exg

    # stín: třídu převezme nejbližší rozhodnutý pixel
    if shadow.any() and decided.any():
        idx = ndimage.distance_transform_edt(~decided, return_distances=False,
                                             return_indices=True)
        green = green[idx[0], idx[1]]
        del idx

    exclude, rural, force_paved = _osm_masks(gdf_osm, (H, W), transform)
    valid = ~nodata & ~exclude

    green_m = green & valid & ~force_paved
    paved_m = ~green & valid & ~rural
    paved_m |= force_paved & valid
    del green

    # vyčištění: otevření/zavření 1 px, malé ostrůvky a díry pryč
    min_px = max(1, int(MIN_AREA_M2 / (px * px)))
    st = ndimage.generate_binary_structure(2, 1)

    def clean(m):
        m = ndimage.binary_opening(m, structure=st)
        m = ndimage.binary_closing(m, structure=st)
        lab, n = ndimage.label(m)
        if n:
            sizes = np.bincount(lab.ravel())
            keep = sizes >= min_px
            keep[0] = False
            m = keep[lab]
        holes = ~m
        lab, n = ndimage.label(holes)
        if n:
            sizes = np.bincount(lab.ravel())
            small = sizes < min_px
            small[0] = False
            m |= small[lab] & valid
        return m

    paved_m = clean(paved_m)
    green_m = clean(green_m) & ~paved_m

    classes = np.zeros((H, W), dtype=np.uint8)
    classes[green_m] = 2
    classes[paved_m] = 1
    del paved_m, green_m

    names = {1: "Orto_zpevneno", 2: "Orto_zelen"}
    rows = []
    for geom, val in shapes(classes, mask=classes > 0, transform=transform, connectivity=4):
        g = shape(geom)
        # schodovité hrany z pixelů → mírné vyhlazení (bez Chaikina,
        # takže simplify na konci nevadí)
        g = g.buffer(px * 0.6, join_style=1).buffer(-px * 0.6, join_style=1)
        g = g.simplify(px * 0.7, preserve_topology=True)
        if g.is_empty or g.area < MIN_AREA_M2:
            continue
        rows.append({"class_name": names[int(val)], "geometry": g})

    gdf = gpd.GeoDataFrame(rows, columns=["class_name", "geometry"],
                           geometry="geometry", crs=crs)
    n_p = int((gdf["class_name"] == "Orto_zpevneno").sum()) if not gdf.empty else 0
    cb(f"Ortofoto: {n_p} zpevněných ploch, {len(gdf) - n_p} ploch zeleně")
    return gdf


def ortho_surface_gdf(extent, crs, gdf_osm=None, rgb_result=None, progress_cb=None):
    """Celý krok: stažení (pokud není předané) + klasifikace. Nikdy nevyhodí —
    při chybě vrátí None, mapa se vygeneruje bez ortofota."""
    try:
        if rgb_result is None:
            rgb_result = fetch_ortho(extent, crs, progress_cb)
        if rgb_result is None:
            return None
        rgb, transform = rgb_result
        gdf = classify_surface(rgb, transform, crs, gdf_osm, progress_cb)
        minx, maxx, miny, maxy = extent
        if not gdf.empty:
            gdf = gpd.clip(gdf, box(minx, miny, maxx, maxy))
        return gdf
    except Exception as e:
        if progress_cb:
            progress_cb(f"Varování ortofoto: {e} — pokračuji bez zpevněných ploch")
        return None