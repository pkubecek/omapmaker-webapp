"""
core/geo_ref.py — georeference výstupů: CRS pro OpenOrienteering Mapper
a směr magnetických poledníků.

OOM při otevření/importu GPKG převede SRS vrstvy na PROJ.4 řetězec
(OSRExportToProj4). U CRS na Besselově elipsoidu (S-JTSK 5514, CH1903+ 2056,
Amersfoort 28992 …) v čistém EPSG WKT chybí TOWGS84, takže PROJ.4 řetězec je
bez +towgs84 a OOM pak data i podklady (OSM, GPS) posouvá o ~100 m. Proto se
do GPKG zapisuje BoundCRS s Helmertovou transformací na WGS84 — nejpřesnější,
jakou PROJ pro dané místo nabízí.
"""

import math
from datetime import date

from pyproj import CRS, Transformer
from pyproj.aoi import AreaOfInterest
from pyproj.transformer import TransformerGroup

_HELMERT = ("Geocentric translations", "Position Vector", "Coordinate Frame")


def horizontal_crs(crs: CRS) -> CRS:
    """Z compound CRS (poloha + výška) vrátí jen polohovou část."""
    if crs.is_compound:
        for sub in crs.sub_crs_list:
            if not sub.is_vertical:
                return sub
    return crs


def crs_label(crs) -> str:
    """'EPSG:xxxx', jinak WKT (oboje bere pyproj/geopandas jako vstup)."""
    crs = CRS.from_user_input(crs)
    epsg = crs.to_epsg()
    return f"EPSG:{epsg}" if epsg else crs.to_wkt()


def crs_for_oom(crs, lon: float, lat: float) -> CRS:
    """CRS pro zápis do GPKG — případně jako BoundCRS s TOWGS84.

    Pokud datum CRS potřebuje k WGS84 nenulový posun, najde se přes PROJ
    nejpřesnější Helmertova (3/7 parametrů) transformace pro místo (lon, lat)
    a CRS se k ní "přiváže". Jinak (ETRS89, WGS84 …) se vrací beze změny.
    """
    src = CRS.from_user_input(crs)
    if src.is_bound or not src.is_projected:
        return src
    try:
        d = 0.01
        tg = TransformerGroup(src, CRS.from_epsg(4326), always_xy=True,
                              area_of_interest=AreaOfInterest(lon - d, lat - d, lon + d, lat + d))
        for t in tg.transformers:
            op = t.to_json_dict()
            for step in op.get("steps", [op]):
                method = step.get("method", {}).get("name", "")
                if step.get("type") != "Transformation" or "geog3D" in method:
                    continue
                if not any(h in method for h in _HELMERT):
                    continue
                values = [p.get("value", 0) for p in step.get("parameters", [])]
                if not any(abs(v) > 1e-9 for v in values):
                    return src          # nulový posun (ETRS89 ≈ WGS84) — není co přidávat
                return CRS.from_json_dict({
                    "type": "BoundCRS",
                    "source_crs": src.to_json_dict(),
                    "target_crs": CRS.from_epsg(4326).to_json_dict(),
                    "transformation": step,
                })
    except Exception as e:
        print(f"[geo_ref] TOWGS84 pro {crs_label(src)} nenalezeno: {e}")
    return src


def _decimal_year(d: date) -> float:
    start = date(d.year, 1, 1)
    days = (date(d.year + 1, 1, 1) - start).days
    return d.year + (d - start).days / days


def magnetic_declination(lon: float, lat: float, when: date | None = None) -> float:
    """Magnetická deklinace (°, + = východní) podle WMM (pygeomag, offline)."""
    from pygeomag import GeoMag
    when = when or date.today()
    try:
        gm = GeoMag(coefficients_file="wmm/WMM_2025.COF")
    except Exception:
        gm = GeoMag()
    res = gm.calculate(glat=lat, glon=lon, alt=0, time=_decimal_year(when),
                       allow_date_outside_lifespan=True)
    return float(res.d)


def true_north_azimuth(crs, lon: float, lat: float) -> float:
    """Úhel zeměpisného severu od severu souřadnicové sítě CRS (°, + = po směru
    hodinových ručiček). Počítá se numericky, takže sedí i pro Křovákovo
    zobrazení (EPSG:5514), kde jsou rozdíly v ČR 6–10°."""
    t = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_user_input(crs), always_xy=True)
    x0, y0 = t.transform(lon, lat - 0.0005)
    x1, y1 = t.transform(lon, lat + 0.0005)
    return math.degrees(math.atan2(x1 - x0, y1 - y0))


def magnetic_north_rotation(crs, lon: float, lat: float, when: date | None = None):
    """Odklon magnetického severu od severu sítě CRS (°, + = po směru hodin).
    Vrací (rotation, declination, true_north_azimuth)."""
    decl = magnetic_declination(lon, lat, when)
    tn = true_north_azimuth(crs, lon, lat)
    return tn + decl, decl, tn
