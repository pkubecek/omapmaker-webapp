"""
Kontrola, že všechny zdroje výškopisu odpovídají (ideálně spustit na Railway,
tím se ověří i síťový přístup odtamtud).

    python -m tools.probe_sources           (z adresáře backend/)
    railway ssh  →  python -m tools.probe_sources

Každý test stáhne jen pár kB až pár MB (malý výřez kolem známého bodu).
"""
import sys
import traceback

sys.path.insert(0, ".")

import numpy as np  # noqa: E402

from app.core import raster_sources as rs  # noqa: E402


def small_bbox(lat, lon, d=0.002):
    return {"min_lat": lat - d, "min_lon": lon - d, "max_lat": lat + d, "max_lon": lon + d}


# (popis, klíč zdroje, lat, lon)
PROBES = [
    ("Bavorsko", "de-BY", 48.137, 11.575), ("Sasko", "de-SN", 51.05, 13.74),
    ("Durynsko", "de-TH", 50.98, 11.03), ("Braniborsko", "de-BB", 52.40, 13.06),
    ("Berlín", "de-BE", 52.52, 13.40), ("Sasko-Anhaltsko", "de-ST", 52.13, 11.63),
    ("Dolní Sasko", "de-NI", 52.37, 9.73), ("Hesensko", "de-HE", 50.11, 8.68),
    ("Severní Porýní-Vestfálsko", "de-NW", 51.23, 6.78), ("Porýní-Falc", "de-RP", 50.00, 8.27),
    ("Sársko", "de-SL", 49.23, 7.00), ("Bádensko-Württembersko", "de-BW", 48.78, 9.18),
    ("Meklenbursko", "de-MV", 54.09, 12.13), ("Šlesvicko-Holštýnsko", "de-SH", 54.32, 10.13),
    ("Hamburk", "de-HH", 53.55, 10.00), ("Brémy", "de-HB", 53.08, 8.80),
    ("Švýcarsko", "ch", 46.948, 7.447), ("Francie", "fr", 45.92, 6.87),
    ("Nizozemsko", "nl", 52.09, 5.12), ("Tyrolsko", "at-tirol", 47.27, 11.40),
    ("Štýrsko", "at-stmk", 47.07, 15.44),
]

ok_all = True
only = {a for a in sys.argv[1:] if not a.startswith("-")}
for label, key, lat, lon in PROBES:
    if only and key not in only:
        continue
    bbox = small_bbox(lat, lon)
    epsg = rs.native_epsg(key, bbox)
    res = {}
    for kind in ("dtm", "dsm"):
        grid = rs.Grid(epsg, bbox)
        ctx = rs.Ctx(grid, bbox, "/tmp", lambda m: None, None)
        try:
            rs.make_source(key).fetch(kind, ctx)
            m = ctx.dtm if kind == "dtm" else (ctx.dsm if np.isfinite(ctx.dsm).any() else ctx.ndsm)
            cov = float(np.isfinite(m).mean())
            res[kind] = f"{cov:.0%}" + (f" (medián {np.nanmedian(m):.1f} m)" if cov else "")
        except Exception as e:
            res[kind] = f"CHYBA: {e}"[:150]
            if "-v" in sys.argv:
                traceback.print_exc()
    good = res["dtm"].endswith(")")
    ok_all &= good
    print(f"{'OK  ' if good else 'FAIL'} {label:28s} DMR {res['dtm']:30s} DMP {res['dsm']}")

sys.exit(0 if ok_all else 1)
