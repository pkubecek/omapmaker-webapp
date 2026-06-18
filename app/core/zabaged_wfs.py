"""
zabaged_wfs.py — stahování ZABAGED® dat přes ArcGIS REST API (ČÚZK).

Endpoint: https://ags.cuzk.gov.cz/arcgis/rest/services/ZABAGED_POLOHOPIS/MapServer/{layerId}/query
- Zdarma, bez registrace
- Žádná diakritika v URL — používá číselné ID vrstev
- bbox v EPSG:5514, výstup GeoJSON
- Paginace přes resultOffset (max 2000 prvků na request)
"""
import time
import requests
import geopandas as gpd
import pandas as pd
from pyproj import Transformer

REST_BASE = "https://ags.cuzk.gov.cz/arcgis/rest/services/ZABAGED_POLOHOPIS/MapServer"
PAGE_SIZE = 2000   # MaxRecordCount vrstev je 2000
MAX_RETRIES = 3
RETRY_DELAY = 3

# Mapování klíčů pipeline → layer ID v MapServeru
# ID zjištěna z https://ags.cuzk.gov.cz/arcgis/rest/services/ZABAGED_POLOHOPIS/MapServer
ZABAGED_LAYERS = {
    "SilniceDalnice":                79,   # Silnice, dálnice
    "Cesta":                         83,   # Cesta
    "Pesina":                        82,   # Pěšina
    "ZeleznicniTrat":                75,   # Železniční trať
    "VodniTok":                      93,   # Vodní tok
    "VodniPlocha":                   132,  # Vodní plocha
    "ElektrickeVedeni":              88,   # Elektrické vedení
    "Zed":                           39,   # Zeď
    "Raseliniste":                   18,   # Rašeliniště (plocha)
    "BazinaMocal":                   131,  # Bažina, močál
    "TrvalyTravniPorost":            141,  # Trvalý travní porost
    "VyznamnyNeboOsamelyStromLesik": 14,   # Významný nebo osamělý strom, lesík
    "OsamelyBalvanSkalaSkalniSuk":   10,   # Osamělý balvan, skála, skalní suk
    "StupenSraz":                    95,   # Stupeň, sráz
    "HradbaValBastaOpevneni":        38,   # Hradba, val, bašta, opevnění
    "ZdrojPodzemnichVod":            19,   # Zdroj podzemních vod
    "MohylaPomnikNahrobek":          25,   # Mohyla, pomník, náhrobek
    "LesniPozemek":                  143,  # Lesní půda se stromy (plocha)
    "SkalniSraz":                    130,  # Skalní útvary
    "Most":                          73,   # Most
    "Ohrada":                        54,   # Zábrana (plot/ohrada)
    "Krmitko":                       None, # Krmítko — není v MapServeru, přeskočit
    "Proseka":                       16,   # Lesní průsek
    "NasupisteHraze":                22,   # Přehradní hráz, jez (nejbližší ekvivalent)
    "HustyPorost":                   144,  # Lesní půda se stromy kategorizovaná
    "OrnaPudaAOstatniDaleNespecifikovanePlochy": 142,  # Orná půda a ostatní plochy
}


def _fetch_page(layer_id: int, bbox_5514: tuple, offset: int,
                progress_cb=None) -> dict | None:
    """Stáhne jednu stránku přes ArcGIS REST /query endpoint."""
    minx, miny, maxx, maxy = bbox_5514
    url = f"{REST_BASE}/{layer_id}/query"
    params = {
        "f": "geojson",
        "geometry": f"{minx},{miny},{maxx},{maxy}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "5514",
        "outSR": "5514",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            # ArcGIS REST vrátí error jako JSON s polem "error"
            if "error" in data:
                raise ValueError(f"ArcGIS error: {data['error']}")
            return data
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                if progress_cb:
                    progress_cb(f"Retry {attempt+1}/{MAX_RETRIES}: {e}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"[zabaged] Chyba layer {layer_id}: {e}")
                return None


def _download_layer(key: str, layer_id: int, bbox_5514: tuple,
                    target_crs: str, progress_cb=None) -> gpd.GeoDataFrame | None:
    """Stáhne celou vrstvu s paginací."""
    frames = []
    offset = 0

    while True:
        data = _fetch_page(layer_id, bbox_5514, offset, progress_cb)
        if data is None:
            break

        features = data.get("features", [])
        if not features:
            break

        try:
            gdf_page = gpd.GeoDataFrame.from_features(features, crs="EPSG:5514")
            frames.append(gdf_page)
        except Exception as e:
            print(f"[zabaged] Parse chyba {key} @{offset}: {e}")
            break

        if progress_cb:
            progress_cb(f"  {key}: {offset + len(features)} prvků")

        # ArcGIS REST vrátí exceededTransferLimit=true pokud jsou další záznamy
        if not data.get("exceededTransferLimit", False):
            break
        offset += PAGE_SIZE

    if not frames:
        return None

    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:5514")

    if target_crs and target_crs != "EPSG:5514":
        try:
            gdf = gdf.to_crs(target_crs)
        except Exception as e:
            print(f"[zabaged] CRS převod {key}: {e}")

    return gdf if not gdf.empty else None


def download_zabaged_wfs(
    bbox_wgs84: tuple,
    target_crs: str = "EPSG:5514",
    progress_cb=None,
) -> dict:
    """
    Stáhne všechny ZABAGED vrstvy (bez budov) pro daný bbox.

    bbox_wgs84: (min_lon, min_lat, max_lon, max_lat) — WGS84
    target_crs: cílový CRS výsledných GeoDataFrames
    progress_cb: volitelná funkce(msg: str)

    Vrací: dict { klíč: GeoDataFrame }
    """
    def cb(msg):
        print(f"[zabaged] {msg}")
        if progress_cb:
            progress_cb(msg)

    # Převod bbox z WGS84 do EPSG:5514
    min_lon, min_lat, max_lon, max_lat = bbox_wgs84
    try:
        t = Transformer.from_crs("EPSG:4326", "EPSG:5514", always_xy=True)
        x1, y1 = t.transform(min_lon, min_lat)
        x2, y2 = t.transform(max_lon, max_lat)
        bbox_5514 = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    except Exception as e:
        cb(f"Varování: CRS transformace selhala ({e})")
        bbox_5514 = (min_lon, min_lat, max_lon, max_lat)

    cb(f"Stahuji ZABAGED REST bbox={bbox_5514}")

    result = {}
    layers = {k: v for k, v in ZABAGED_LAYERS.items() if v is not None}
    total = len(layers)

    for i, (key, layer_id) in enumerate(layers.items(), 1):
        cb(f"[{i}/{total}] {key} (layer {layer_id})...")
        try:
            gdf = _download_layer(key, layer_id, bbox_5514, target_crs, cb)
            if gdf is not None and not gdf.empty:
                result[key] = gdf
                cb(f"  OK: {key} — {len(gdf)} prvků")
            else:
                cb(f"  Prázdná vrstva: {key}")
        except Exception as e:
            cb(f"  Chyba {key}: {e}")

    cb(f"ZABAGED hotovo: {len(result)}/{total} vrstev staženo")
    return result