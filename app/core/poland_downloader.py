"""
poland_downloader.py — stahování LiDAR dlaždic z polského GUGiK geoportálu.

Polský geoportal (GUGiK) poskytuje LiDAR point cloudy (LAZ) a NMT/NMPT (GeoTIFF)
přes WFS službu. Dlaždice se vybírají podle bbox v EPSG:4326, atribut
url_do_pobrania obsahuje přímý odkaz ke stažení.

DTM (NMT - Numeryczny Model Terenu):
  WFS: https://mapy.geoportal.gov.pl/wss/service/PZGIK/NumerycznyModelTerenuEVRF2007/WFS/Skorowidze
  TypeName: gugik:SkorowidzNumerycznegoModeluTerenu{YEAR}
  Formát: GeoTIFF (ARC/INFO ASCII Grid), CRS EPSG:2180

DSM (NMPT - Numeryczny Model Powierzchni Terenu):
  WFS: https://mapy.geoportal.gov.pl/wss/service/PZGIK/NumerycznyModelPowierzchniEVRF2007/WFS/Skorowidze
  TypeName: gugik:SkorowidzNumerycznegoModeluPowierzchniTerenu{YEAR}
  Formát: GeoTIFF, CRS EPSG:2180

LiDAR point cloudy (alternativa k NMT):
  WFS: https://mapy.geoportal.gov.pl/wss/service/PZGIK/DanePomiaroweLidarEVRF2007/WFS/Skorowidze
  TypeName: gugik:SkorowidzDanychPomiarowychLIDAR{YEAR}
  Formát: LAZ, CRS EPSG:2180

Výstupní CRS dat: EPSG:2180 (PL-2000 PUWG 1992 / GRS80)
"""
import os
import ssl
import zipfile
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import numpy as np
from pyproj import CRS, Transformer

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# -------------------------------------------------------------------------
# WFS endpoints
# -------------------------------------------------------------------------
_WFS_LIDAR = (
    "https://mapy.geoportal.gov.pl/wss/service/PZGIK"
    "/DanePomiaroweLidarEVRF2007/WFS/Skorowidze"
)
_WFS_NMT = (
    "https://mapy.geoportal.gov.pl/wss/service/PZGIK"
    "/NumerycznyModelTerenuEVRF2007/WFS/Skorowidze"
)
_WFS_NMPT = (
    "https://mapy.geoportal.gov.pl/wss/service/PZGIK"
    "/NumerycznyModelPowierzchniEVRF2007/WFS/Skorowidze"
)

# Roky dostupných dat (od nejnovějšího) — WFS má vrstvy per rok
_LIDAR_YEARS = [2021, 2020, 2019, 2018]
_NMT_YEARS   = [2021, 2020, 2019, 2018, 2017, 2016, 2015]
_NMPT_YEARS  = [2021, 2020, 2019, 2018, 2017]

_HEADERS = {"User-Agent": "OMapMaker/7 (orienteering map tool)"}


def _wfs_get_feature(wfs_url: str, type_name: str,
                     bbox_wgs84: tuple, max_features: int = 500) -> list[dict]:
    """
    Volá WFS GetFeature a vrátí seznam dlaždic jako dict s klíčem 'url'.
    bbox_wgs84: (min_lat, min_lon, max_lat, max_lon)
    Vrátí: [{"url": "https://...", "name": "...", "geom_bbox": (...)}]
    """
    mn_lat, mn_lon, mx_lat, mx_lon = bbox_wgs84
    # GUGiK WFS chce BBOX jako lon,lat (EPSG:4326 s urn CRS)
    bbox_str = f"{mn_lon},{mn_lat},{mx_lon},{mx_lat},urn:ogc:def:crs:EPSG::4326"

    url = (
        f"{wfs_url}?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
        f"&TYPENAMES={type_name}"
        f"&SRSNAME=urn:ogc:def:crs:EPSG::4326"
        f"&BBOX={bbox_str}"
        f"&COUNT={max_features}"
    )
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as resp:
            raw = resp.read()
    except Exception as e:
        print(f"[pl_downloader] WFS chyba ({type_name}): {e}")
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"[pl_downloader] WFS XML parse chyba: {e}")
        return []

    # Namespaces v odpovědi GUGiK
    ns = {
        "wfs": "http://www.opengis.net/wfs/2.0",
        "gugik": "http://gugik.gov.pl",
        "gml": "http://www.opengis.net/gml/3.2",
    }

    tiles = []
    # Hledáme url_do_pobrania v libovolném namespace
    for member in root.iter():
        # Najdi element s URL ke stažení
        url_elem = None
        # Zkus různé možné názvy elementu
        for tag_suffix in ["url_do_pobrania", "URL_do_pobrania", "urlDoPobrania", "url"]:
            url_elem = member.find(f"gugik:{tag_suffix}", ns)
            if url_elem is None:
                # Zkus bez namespace
                url_elem = member.find(tag_suffix)
            if url_elem is not None and url_elem.text:
                break

        if url_elem is None or not url_elem.text:
            continue

        download_url = url_elem.text.strip()
        if not (download_url.startswith("http") and
                any(download_url.lower().endswith(ext)
                    for ext in [".laz", ".las", ".zip", ".tif", ".tiff", ".asc"])):
            continue

        # Název dlaždice
        name_elem = member.find("gugik:nazwa_pliku", ns) or member.find("nazwa_pliku")
        name = name_elem.text.strip() if name_elem is not None and name_elem.text else \
               os.path.basename(download_url)

        tiles.append({"url": download_url, "name": name})

    return tiles


def _query_tiles(wfs_url: str, years: list[int],
                 type_prefix: str, bbox_wgs84: tuple,
                 progress_cb=None) -> list[dict]:
    """
    Prochází roky od nejnovějšího a sbírá dlaždice pokrývající bbox.
    Každá dlaždice se započítá jen jednou (preferuje novější rok).
    """
    seen_names = set()
    all_tiles = []

    for year in years:
        type_name = f"gugik:{type_prefix}{year}"
        if progress_cb:
            progress_cb(f"Dotazuji WFS {type_name}...")
        tiles = _wfs_get_feature(wfs_url, type_name, bbox_wgs84)
        new_tiles = []
        for t in tiles:
            if t["name"] not in seen_names:
                seen_names.add(t["name"])
                new_tiles.append(t)
        if new_tiles:
            all_tiles.extend(new_tiles)
            if progress_cb:
                progress_cb(f"  rok {year}: {len(new_tiles)} nových dlaždic")

    return all_tiles


def _download_file(url: str, dest_path: str, progress_cb=None) -> bool:
    """Stáhne jeden soubor. Vrátí True při úspěchu."""
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=300, context=_SSL_CTX) as r, \
             open(dest_path, "wb") as f:
            f.write(r.read())
        return True
    except Exception as e:
        if progress_cb:
            progress_cb(f"  Chyba stahování {os.path.basename(url)}: {e}")
        return False


def _extract_if_zip(zip_path: str, dest_dir: str) -> list[str]:
    """Rozbalí ZIP a vrátí seznam extrahovaných souborů."""
    extracted = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if name.lower().endswith((".laz", ".las", ".tif", ".tiff", ".asc")):
                    zf.extract(name, dest_dir)
                    extracted.append(os.path.join(dest_dir, name))
        os.remove(zip_path)
    except Exception as e:
        print(f"[pl_downloader] ZIP chyba {zip_path}: {e}")
    return extracted


def _merge_tif_to_laz(tif_paths: list[str], output_laz: str,
                       progress_cb=None) -> bool:
    """
    Konvertuje rastrové GeoTIFF/ASC soubory NMT do LAZ formátu kompatibilního
    s pipeline.py (klasifikace bodů jako ground class=2).
    """
    try:
        import rasterio
        import laspy

        all_x, all_y, all_z = [], [], []
        src_crs = None

        for tif_path in tif_paths:
            if progress_cb:
                progress_cb(f"  Konvertuji {os.path.basename(tif_path)}...")
            with rasterio.open(tif_path) as src:
                if src_crs is None:
                    src_crs = src.crs
                data = src.read(1)
                nodata = src.nodata
                rows, cols = np.where(data != nodata if nodata is not None else np.ones_like(data, dtype=bool))
                xs, ys = rasterio.transform.xy(src.transform, rows, cols)
                zs = data[rows, cols].astype(np.float64)
                valid = np.isfinite(zs) & (zs > -9000)
                all_x.append(np.array(xs)[valid])
                all_y.append(np.array(ys)[valid])
                all_z.append(zs[valid])

        if not all_x:
            return False

        x = np.concatenate(all_x)
        y = np.concatenate(all_y)
        z = np.concatenate(all_z)

        header = laspy.LasHeader(point_format=0, version="1.2")
        header.scales = np.array([0.01, 0.01, 0.01])
        header.offsets = np.array([x.min(), y.min(), z.min()])

        # Uložíme CRS jako WKT do VLR
        if src_crs is not None:
            try:
                wkt = src_crs.to_wkt()
                header.vlrs.append(laspy.LasAppender.make_vlr(
                    user_id="LASF_Projection",
                    record_id=2112,
                    description="OGC Coordinate System WKT",
                    record_data=wkt.encode("utf-8"),
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
            progress_cb(f"  Zapsáno {len(x):,} bodů → {os.path.basename(output_laz)}")
        return True

    except Exception as e:
        print(f"[pl_downloader] Konverze TIF→LAZ chyba: {e}")
        import traceback; traceback.print_exc()
        return False


def download_poland(
    bbox: dict,
    out_dir: str,
    use_lidar_point_cloud: bool = True,
    progress_cb=None,
) -> dict:
    """
    Hlavní funkce: stáhne DTM a DSM pro daný bbox z polského GUGiK.

    bbox: { min_lat, min_lon, max_lat, max_lon }  (WGS84)
    out_dir: výstupní složka
    use_lidar_point_cloud: True = stáhne LiDAR LAZ (lepší kvalita),
                           False = stáhne NMT rastr (rychlejší, menší)

    Vrací: { dmr_path, dmp_path, crs }
      crs = "EPSG:2180" (PL-2000 PUWG 1992)
      dmr_path = LAZ soubor s DTM
      dmp_path = LAZ nebo TIF soubor s DSM (nebo "" pokud nedostupný)
    """
    os.makedirs(out_dir, exist_ok=True)

    mn_lat = bbox["min_lat"]
    mn_lon = bbox["min_lon"]
    mx_lat = bbox["max_lat"]
    mx_lon = bbox["max_lon"]
    bbox_wgs84 = (mn_lat, mn_lon, mx_lat, mx_lon)

    def cb(msg):
        print(f"[pl_downloader] {msg}")
        if progress_cb:
            progress_cb(msg)

    # -------------------------------------------------------------------------
    # DTM
    # -------------------------------------------------------------------------
    dtm_raw_dir = os.path.join(out_dir, "dtm_tiles")
    os.makedirs(dtm_raw_dir, exist_ok=True)
    dtm_files = []

    if use_lidar_point_cloud:
        cb("Hledám LiDAR dlaždice (DTM)...")
        lidar_tiles = _query_tiles(
            _WFS_LIDAR, _LIDAR_YEARS,
            "SkorowidzDanychPomiarowychLIDAR",
            bbox_wgs84, progress_cb=cb,
        )
        if lidar_tiles:
            cb(f"Stahuju {len(lidar_tiles)} LiDAR dlaždic...")
            for i, tile in enumerate(lidar_tiles, 1):
                cb(f"  LiDAR {i}/{len(lidar_tiles)}: {tile['name']}")
                ext = os.path.splitext(tile["url"])[1].lower()
                dest = os.path.join(dtm_raw_dir, tile["name"] + (ext if ext else ".laz"))
                if _download_file(tile["url"], dest, cb):
                    if ext == ".zip":
                        dtm_files.extend(_extract_if_zip(dest, dtm_raw_dir))
                    else:
                        dtm_files.append(dest)
        else:
            cb("LiDAR dlaždice nenalezeny, zkouším NMT rastr...")
            use_lidar_point_cloud = False

    if not use_lidar_point_cloud or not dtm_files:
        cb("Hledám NMT (rastr DTM) dlaždice...")
        nmt_tiles = _query_tiles(
            _WFS_NMT, _NMT_YEARS,
            "SkorowidzNumerycznegoModeluTerenu",
            bbox_wgs84, progress_cb=cb,
        )
        cb(f"Stahuju {len(nmt_tiles)} NMT dlaždic...")
        nmt_tif_files = []
        for i, tile in enumerate(nmt_tiles, 1):
            cb(f"  NMT {i}/{len(nmt_tiles)}: {tile['name']}")
            ext = os.path.splitext(tile["url"])[1].lower()
            dest = os.path.join(dtm_raw_dir, tile["name"] + (ext if ext else ".tif"))
            if _download_file(tile["url"], dest, cb):
                if ext == ".zip":
                    extracted = _extract_if_zip(dest, dtm_raw_dir)
                    nmt_tif_files.extend(extracted)
                elif ext in (".tif", ".tiff", ".asc"):
                    nmt_tif_files.append(dest)

        if not nmt_tif_files:
            raise RuntimeError("Žádné DTM dlaždice pro zadanou oblast. Je oblast v Polsku?")

        # Konvertuj TIF → LAZ (pipeline.py očekává LAZ jako vstup DTM)
        cb("Konvertuji NMT rastr → LAZ...")
        dtm_laz = os.path.join(out_dir, "PL_NMT_merged.laz")
        ok = _merge_tif_to_laz(nmt_tif_files, dtm_laz, cb)
        if not ok:
            raise RuntimeError("Konverze NMT TIF → LAZ selhala.")
        dtm_files = [dtm_laz]

    # Merge LAZ dlaždic do jednoho souboru
    dtm_merged = os.path.join(out_dir, "PL_LiDAR_DTM_merged.laz")
    if len(dtm_files) == 1 and dtm_files[0].endswith(".laz"):
        import shutil
        shutil.copy2(dtm_files[0], dtm_merged)
    elif dtm_files:
        cb("Merguji DTM dlaždice...")
        from .downloader import merge_laz_files  # z ČÚZK downloaderu
        ok = merge_laz_files(dtm_files, dtm_merged, clip_bbox_wgs84=bbox_wgs84)
        if not ok:
            raise RuntimeError("Merge DTM LAZ selhal.")
    else:
        raise RuntimeError("Žádné DTM soubory k mergování.")

    # -------------------------------------------------------------------------
    # DSM (NMPT)
    # -------------------------------------------------------------------------
    dmp_merged = ""
    dmp_raw_dir = os.path.join(out_dir, "dmp_tiles")
    os.makedirs(dmp_raw_dir, exist_ok=True)

    cb("Hledám NMPT (DSM) dlaždice...")
    nmpt_tiles = _query_tiles(
        _WFS_NMPT, _NMPT_YEARS,
        "SkorowidzNumerycznegoModeluPowierzchniTerenu",
        bbox_wgs84, progress_cb=cb,
    )

    if nmpt_tiles:
        cb(f"Stahuju {len(nmpt_tiles)} NMPT dlaždic...")
        nmpt_tif_files = []
        for i, tile in enumerate(nmpt_tiles, 1):
            cb(f"  NMPT {i}/{len(nmpt_tiles)}: {tile['name']}")
            ext = os.path.splitext(tile["url"])[1].lower()
            dest = os.path.join(dmp_raw_dir, tile["name"] + (ext if ext else ".tif"))
            if _download_file(tile["url"], dest, cb):
                if ext == ".zip":
                    extracted = _extract_if_zip(dest, dmp_raw_dir)
                    nmpt_tif_files.extend(extracted)
                elif ext in (".tif", ".tiff", ".asc"):
                    nmpt_tif_files.append(dest)

        if nmpt_tif_files:
            cb("Konvertuji NMPT rastr → LAZ...")
            dmp_laz = os.path.join(out_dir, "PL_NMPT_merged.laz")
            ok = _merge_tif_to_laz(nmpt_tif_files, dmp_laz, cb)
            if ok:
                dmp_merged = dmp_laz
    else:
        cb("NMPT dlaždice nenalezeny — DSM nebude k dispozici.")

    cb("Hotovo!")
    return {
        "dmr_path": dtm_merged,
        "dmp_path": dmp_merged,
        "crs": "EPSG:2180",
    }