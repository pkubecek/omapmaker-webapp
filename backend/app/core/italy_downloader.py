"""
core/italy_downloader.py — stažení DTM pro Sicílii z regionálního
SITR (Sistema Informativo Territoriale Regionale) geoportálu.

Zdroj: modelli_digitali/mdt_2013 (Esri ImageServer), rozlišení 2x2m,
CRS EPSG:25833 (UTM 33N), nálet ATA 2012-2013, licence CC BY.

POZOR: SITR nepublikuje DSM (jen DTM + odvozený sklon) — dmp_path
vrací prázdný řetězec, pipeline poběží bez vegetační vrstvy (stejné
chování jako když DSM chybí u ostatních zdrojů).

Používá nativní Esri REST operaci exportImage (ne WCS — ten server
na WCS GetCoverage spolehlivě odpovídá 400/404, zatímco exportImage
je zdokumentovaná a funkční REST operace stejného ImageServeru).
Stažený GeoTIFF se převádí na LAZ (ground-classified body), aby ho
pipeline.py mohl zpracovat stejnou cestou jako ostatní DTM zdroje
(load_dmr_grid očekává .las/.laz).
"""

import os
import urllib.request
import urllib.parse
import ssl

import numpy as np
from pyproj import Transformer

_EXPORT_IMAGE_URL = "https://map.sitr.regione.sicilia.it/gis/rest/services/modelli_digitali/mdt_2013/ImageServer/exportImage"
_SRC_CRS = "EPSG:25833"
_PIXEL_SIZE_M = 2.0  # nativní rozlišení zdroje

# Esri server limity (z ImageServer metadata) — nad tohle nemá smysl žádat
_MAX_IMAGE_WIDTH = 15000
_MAX_IMAGE_HEIGHT = 4100

_HEADERS = {"User-Agent": "Mozilla/5.0 (OMapMaker)"}
_SSL_CTX = ssl.create_default_context()

# SITR mdt_2013 plný extent (viz ArcGIS REST metadata) — mimo tohle
# nemá smysl posílat request, server by vrátil prázdné/chybové pokrytí
_FULL_EXTENT = (224674.0, 3929228.0, 558320.0, 4296652.0)


def _bbox_wgs84_to_25833(bbox_wgs84: tuple) -> tuple:
    """bbox_wgs84: (min_lat, min_lon, max_lat, max_lon) -> (minx, miny, maxx, maxy) v EPSG:25833."""
    mn_lat, mn_lon, mx_lat, mx_lon = bbox_wgs84
    t = Transformer.from_crs("EPSG:4326", _SRC_CRS, always_xy=True)
    x0, y0 = t.transform(mn_lon, mn_lat)
    x1, y1 = t.transform(mx_lon, mx_lat)
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _download_dtm_tiff(bbox_25833: tuple, dest_path: str, progress_cb=None) -> bool:
    """Stáhne GeoTIFF výřez přes Esri ImageServer exportImage operaci."""
    minx, miny, maxx, maxy = bbox_25833

    width = int((maxx - minx) / _PIXEL_SIZE_M)
    height = int((maxy - miny) / _PIXEL_SIZE_M)
    width = max(1, min(width, _MAX_IMAGE_WIDTH))
    height = max(1, min(height, _MAX_IMAGE_HEIGHT))

    params = {
        "bbox": f"{minx:.2f},{miny:.2f},{maxx:.2f},{maxy:.2f}",
        "bboxSR": "25833",
        "imageSR": "25833",
        "size": f"{width},{height}",
        "format": "tiff",
        "pixelType": "F32",
        "noDataInterpretation": "esriNoDataMatchAny",
        "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }
    url = f"{_EXPORT_IMAGE_URL}?{urllib.parse.urlencode(params)}"

    if progress_cb:
        progress_cb("Stahuji DTM z SITR (exportImage)...")
    print(f"[it_downloader] exportImage URL: {url}")

    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=120, context=_SSL_CTX) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "")
    except Exception as e:
        print(f"[it_downloader] exportImage chyba: {e}")
        return False

    # Když f=image selže/validace neprojde, Esri server někdy i tak vrátí
    # JSON s chybovou hláškou místo TIFF bajtů — ověř to
    if "json" in content_type.lower() or data[:1] == b"{":
        print(f"[it_downloader] Server vrátil JSON místo obrázku: {data[:500]}")
        return False

    with open(dest_path, "wb") as f:
        f.write(data)

    if progress_cb:
        progress_cb(f"DTM staženo ({len(data) / 1e6:.1f} MB)")
    return True


def _tif_to_laz(tif_path: str, output_laz: str, progress_cb=None) -> bool:
    """
    Převede jednopásmový výškový GeoTIFF na LAZ (ground-classified body),
    aby ho pipeline.py mohl zpracovat stejnou cestou jako LiDAR LAZ vstupy.
    """
    try:
        import rasterio
        import laspy

        if progress_cb:
            progress_cb("Konvertuji GeoTIFF -> LAZ...")

        with rasterio.open(tif_path) as src:
            data = src.read(1)
            nodata = src.nodata
            rows, cols = np.where(
                data != nodata if nodata is not None else np.ones_like(data, dtype=bool)
            )
            xs, ys = rasterio.transform.xy(src.transform, rows, cols)
            zs = data[rows, cols].astype(np.float64)
            valid = np.isfinite(zs) & (zs > -100) & (zs < 5000)
            x = np.array(xs)[valid]
            y = np.array(ys)[valid]
            z = zs[valid]
            src_crs_wkt = src.crs.to_wkt() if src.crs else None

        if len(x) == 0:
            print("[it_downloader] Po filtraci nezůstaly žádné platné body.")
            return False

        header = laspy.LasHeader(point_format=0, version="1.2")
        header.scales = np.array([0.01, 0.01, 0.01])
        header.offsets = np.array([x.min(), y.min(), z.min()])

        if src_crs_wkt:
            try:
                header.vlrs.append(laspy.LasAppender.make_vlr(
                    user_id="LASF_Projection",
                    record_id=2112,
                    description="OGC Coordinate System WKT",
                    record_data=src_crs_wkt.encode("utf-8"),
                ))
            except Exception:
                pass

        las = laspy.LasData(header=header)
        las.x = x
        las.y = y
        las.z = z
        las.classification = np.full(len(x), 2, dtype=np.uint8)  # ground
        las.write(output_laz)

        if progress_cb:
            progress_cb(f"Zapsáno {len(x):,} bodů -> {os.path.basename(output_laz)}")
        return True

    except Exception as e:
        print(f"[it_downloader] Konverze TIF->LAZ chyba: {e}")
        import traceback
        traceback.print_exc()
        return False


def download_italy(bbox: dict, out_dir: str, progress_cb=None) -> dict:
    """
    Hlavní funkce: stáhne DTM pro Sicílii z regionálního SITR WCS.

    bbox: { min_lat, min_lon, max_lat, max_lon }  (WGS84)
    out_dir: výstupní složka

    Vrací: { dmr_path, dmp_path, crs }
      crs = "EPSG:25833"
      dmr_path = LAZ soubor s DTM
      dmp_path = "" (SITR DSM nepublikuje — mapa bude bez vegetace)
    """
    os.makedirs(out_dir, exist_ok=True)

    def cb(msg):
        print(f"[it_downloader] {msg}")
        if progress_cb:
            progress_cb(msg)

    bbox_wgs84 = (bbox["min_lat"], bbox["min_lon"], bbox["max_lat"], bbox["max_lon"])
    bbox_25833 = _bbox_wgs84_to_25833(bbox_wgs84)

    minx, miny, maxx, maxy = bbox_25833
    ex0, ey0, ex1, ey1 = _FULL_EXTENT
    if maxx < ex0 or minx > ex1 or maxy < ey0 or miny > ey1:
        raise RuntimeError(
            "Vybraná oblast je mimo pokrytí sicilského SITR DTM "
            f"(extent EPSG:25833: {_FULL_EXTENT}). Je oblast na Sicílii?"
        )

    # Malý buffer 50m pro okrajové efekty interpolace
    BUFFER = 50
    bbox_25833 = (minx - BUFFER, miny - BUFFER, maxx + BUFFER, maxy + BUFFER)

    tif_path = os.path.join(out_dir, "IT_SITR_DTM_2m.tif")
    cb("Stahuji DTM (mdt_2013, 2m) z SITR Sicilia...")
    ok = _download_dtm_tiff(bbox_25833, tif_path, progress_cb=cb)
    if not ok:
        raise RuntimeError("Stažení DTM ze SITR WCS selhalo.")

    dtm_laz = os.path.join(out_dir, "IT_SITR_DTM_merged.laz")
    ok = _tif_to_laz(tif_path, dtm_laz, progress_cb=cb)
    if not ok:
        raise RuntimeError("Konverze DTM GeoTIFF -> LAZ selhala.")

    cb("DSM není u SITR k dispozici — mapa bude bez vegetace.")
    cb("Hotovo!")

    return {
        "dmr_path": dtm_laz,
        "dmp_path": "",
        "crs": "EPSG:25833",
    }