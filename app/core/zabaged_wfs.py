"""
zabaged_wfs.py — stahování ZABAGED® dat přes WFS službu ČÚZK.

Endpoint: https://ags.cuzk.gov.cz/arcgis/services/ZABAGED_POLOHOPIS/MapServer/WFSServer
- Zdarma, bez registrace, licence CC BY 4.0
- Výchozí CRS: EPSG:5514
- Limit: 1000 prvků na request, paginace přes startindex
- Výstup: GEOJSON
- Používá POST + XML body kvůli diakritice v názvech vrstev
- bbox se posílá ve WGS84 (lon,lat,lon,lat) bez CRS suffixu
"""
import time
import requests
import geopandas as gpd
import pandas as pd
from pyproj import Transformer

WFS_URL = "https://ags.cuzk.gov.cz/arcgis/services/ZABAGED_POLOHOPIS/MapServer/WFSServer"
PAGE_SIZE = 1000
MAX_RETRIES = 3
RETRY_DELAY = 3  # sekund

# Mapování klíčů pipeline → název WFS vrstvy
# Názvy jsou přesně z GetCapabilities (s diakritikou)
ZABAGED_LAYERS = {
    "SilniceDalnice":                "ZABAGED_POLOHOPIS:Silnice__dálnice",
    "Cesta":                         "ZABAGED_POLOHOPIS:Cesta",
    "Pesina":                        "ZABAGED_POLOHOPIS:Pěšina__turistická_stezka",
    "ZeleznicniTrat":                "ZABAGED_POLOHOPIS:Železniční_trať",
    "VodniTok":                      "ZABAGED_POLOHOPIS:Vodní_tok",
    "VodniPlocha":                   "ZABAGED_POLOHOPIS:Vodní_plocha",
    "ElektrickeVedeni":              "ZABAGED_POLOHOPIS:Elektrické_vedení",
    "Zed":                           "ZABAGED_POLOHOPIS:Zeď",
    "Raseliniste":                   "ZABAGED_POLOHOPIS:Rašeliniště",
    "BazinaMocal":                   "ZABAGED_POLOHOPIS:Bažina__močál",
    "TrvalyTravniPorost":            "ZABAGED_POLOHOPIS:Trvalý_travní_porost",
    "VyznamnyNeboOsamelyStromLesik": "ZABAGED_POLOHOPIS:Významný_nebo_osamělý_strom__lesík",
    "OsamelyBalvanSkalaSkalniSuk":   "ZABAGED_POLOHOPIS:Osamělý_balvan__skála__skalní_suk",
    "StupenSraz":                    "ZABAGED_POLOHOPIS:Stupeň__sráz",
    "HradbaValBastaOpevneni":        "ZABAGED_POLOHOPIS:Hradba__val__bašta__opevnění",
    "ZdrojPodzemnichVod":            "ZABAGED_POLOHOPIS:Zdroj_podzemních_vod",
    "MohylaPomnikNahrobek":          "ZABAGED_POLOHOPIS:Mohyla__pomník__náhrobek",
    "LesniPozemek":                  "ZABAGED_POLOHOPIS:Lesní_pozemek",
    "SkalniSraz":                    "ZABAGED_POLOHOPIS:Skalní_sráz__výchoz",
    "Most":                          "ZABAGED_POLOHOPIS:Most",
    "Ohrada":                        "ZABAGED_POLOHOPIS:Ohrada__plot",
    "Krmitko":                       "ZABAGED_POLOHOPIS:Krmítko",
    "Proseka":                       "ZABAGED_POLOHOPIS:Průsek",
    "NasupisteHraze":                "ZABAGED_POLOHOPIS:Násyp__hráz",
    "HustyPorost":                   "ZABAGED_POLOHOPIS:Hustý_porost",
    "OrnaPudaAOstatniDaleNespecifikovanePlochy": "ZABAGED_POLOHOPIS:Orná_půda_a_ostatní_dále_nespecifikované_plochy",
}


def _build_xml_request(typename: str, bbox_wgs84: tuple, startindex: int) -> str:
    """
    Sestaví WFS 2.0 GetFeature XML request.
    POST + XML správně řeší UTF-8 v názvech vrstev.
    bbox_wgs84: (min_lon, min_lat, max_lon, max_lat)
    """
    min_lon, min_lat, max_lon, max_lat = bbox_wgs84
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:GetFeature
    service="WFS"
    version="2.0.0"
    outputFormat="GEOJSON"
    count="{PAGE_SIZE}"
    startIndex="{startindex}"
    xmlns:wfs="http://www.opengis.net/wfs/2.0"
    xmlns:fes="http://www.opengis.net/fes/2.0"
    xmlns:gml="http://www.opengis.net/gml/3.2"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd">
  <wfs:Query typeNames="{typename}">
    <fes:Filter>
      <fes:BBOX>
        <gml:Envelope srsName="urn:ogc:def:crs:OGC:1.3:CRS84">
          <gml:lowerCorner>{min_lon} {min_lat}</gml:lowerCorner>
          <gml:upperCorner>{max_lon} {max_lat}</gml:upperCorner>
        </gml:Envelope>
      </fes:BBOX>
    </fes:Filter>
  </wfs:Query>
</wfs:GetFeature>"""


def _fetch_page(typename: str, bbox_wgs84: tuple, startindex: int,
                progress_cb=None) -> dict | None:
    """Stáhne jednu stránku GeoJSON dat přes POST XML request."""
    xml_body = _build_xml_request(typename, bbox_wgs84, startindex)
    headers = {"Content-Type": "application/xml; charset=utf-8"}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                WFS_URL, data=xml_body.encode("utf-8"),
                headers=headers, timeout=60,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                if progress_cb:
                    progress_cb(f"Retry {attempt+1}/{MAX_RETRIES}: {e}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"[zabaged_wfs] Chyba {typename}: {e}")
                return None


def _download_layer(key: str, typename: str, bbox_wgs84: tuple,
                    target_crs: str, progress_cb=None) -> gpd.GeoDataFrame | None:
    """Stáhne celou vrstvu s paginací."""
    frames = []
    startindex = 0

    while True:
        data = _fetch_page(typename, bbox_wgs84, startindex, progress_cb)
        if data is None:
            break

        features = data.get("features", [])
        if not features:
            break

        try:
            gdf_page = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
            frames.append(gdf_page)
        except Exception as e:
            print(f"[zabaged_wfs] Parse chyba {key} @{startindex}: {e}")
            break

        if progress_cb:
            progress_cb(f"  {key}: {startindex + len(features)} prvků")

        if len(features) < PAGE_SIZE:
            break
        startindex += PAGE_SIZE

    if not frames:
        return None

    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")

    # Převod do cílového CRS
    try:
        gdf = gdf.to_crs(target_crs)
    except Exception as e:
        print(f"[zabaged_wfs] CRS převod {key}: {e}")

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

    Vrací: dict { klíč: GeoDataFrame } — stejná struktura jako zabaged_gdfs v pipeline
    """
    def cb(msg):
        print(f"[zabaged_wfs] {msg}")
        if progress_cb:
            progress_cb(msg)

    min_lon, min_lat, max_lon, max_lat = bbox_wgs84
    cb(f"Stahuji ZABAGED WFS bbox=({min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f})")

    result = {}
    total = len(ZABAGED_LAYERS)

    for i, (key, typename) in enumerate(ZABAGED_LAYERS.items(), 1):
        cb(f"[{i}/{total}] {key}...")
        try:
            gdf = _download_layer(key, typename, bbox_wgs84, target_crs, cb)
            if gdf is not None and not gdf.empty:
                result[key] = gdf
                cb(f"  OK: {key} — {len(gdf)} prvků")
            else:
                cb(f"  Prázdná vrstva: {key}")
        except Exception as e:
            cb(f"  Chyba {key}: {e}")

    cb(f"ZABAGED WFS hotovo: {len(result)}/{total} vrstev staženo")
    return result