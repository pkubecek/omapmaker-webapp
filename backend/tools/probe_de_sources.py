"""
Rychlá kontrola, že zdroje DMR/DMP pro Bavorsko a Sasko odpovídají.

Spuštění (z adresáře backend/):   python -m tools.probe_de_sources
Na Railway (ověří i egress):     railway ssh  →  python -m tools.probe_de_sources

Pro každý zdroj stáhne prvních pár kB jedné známé dlaždice a ověří, že je to
opravdu TIFF / ZIP (ne HTML chybová stránka).
"""
import sys

import requests

sys.path.insert(0, ".")
from app.core.germany_downloader import SOURCES, _url, _looks_valid, _HEADERS  # noqa: E402

# Dlaždice ověřené autorem knihovny geokachel (2026-09-20).
PROBES = [("BY", 690, 5334), ("SN", 278, 5590)]

ok_all = True
for state, e, n in PROBES:
    for kind in ("dtm", "dsm"):
        url = _url(state, kind, e, n)
        try:
            with requests.get(url, headers=_HEADERS, timeout=30, stream=True) as r:
                head = next(r.iter_content(4096), b"")
                ok = r.status_code == 200 and _looks_valid(head, SOURCES[state]["zipped"])
                info = f"HTTP {r.status_code}, {r.headers.get('Content-Length', '?')} B"
        except Exception as ex:
            ok, info = False, str(ex)
        ok_all &= ok
        print(f"{'OK  ' if ok else 'FAIL'} {state} {kind}: {info}\n     {url}")

sys.exit(0 if ok_all else 1)
