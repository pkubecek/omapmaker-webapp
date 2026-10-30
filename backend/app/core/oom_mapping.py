"""
oom_mapping.py — převod interních sym_keys (symbols*.xml) na čísla symbolů
v oficiálních OOM sadách (OpenOrienteering Mapper "symbol sets"):

  - ISOM 2017-2   (1:10 000 / 1:15 000)  → standard "isom"
  - ISSprOM 2019  (1:4 000)              → standard "issprom"

Proč: GPKG vrstvy se v OOM párují se symboly přes CRT soubor
(`<číslo symbolu>  Layer = <název vrstvy>`). OOM přiřadí symbol jen když
  1) číslo symbolu v CRT v cílové sadě opravdu existuje, a
  2) typ objektu sedí s typem symbolu (bodový objekt ↔ bodový symbol,
     linie/polygon ↔ liniový/plošný/kombinovaný symbol) — jinak
     Object::setSymbol() potichu selže a objekt zůstane s importním symbolem.
Proto exporter pojmenovává vrstvy rovnou cílovým OOM číslem (`isom_<číslo>`)
a geometrii případně převede na typ, který cílový symbol přijme. CRT je pak
jen identita "číslo → isom_<číslo>" (viz write_crt()).

Tabulky typů jsou vytažené z OOM šablon
  symbol sets/10000/ISOM 2017-2_10000.omap  (15000 má identická čísla i typy)
  symbol sets/4000/ISSprOM 2019_4000.omap
p = bod, l = linie, a = plocha, c = kombinovaný (linie/plocha).
"""
import re


def _types(**groups) -> dict:
    out = {}
    for t, codes in groups.items():
        for code in codes.split():
            out.setdefault(code, t)
    return out


_ISOM_TYPES = _types(
    p="101.1 103.1 104.1 104.9 109 110 111 112 113.1 115 201.1 201.9 202.1 202.3 202.9 203.1 203.2 203.9 204 204.5 205 207 207.1 208.1 208.2 210.1 303 308.1 310.1 311 312 313 417 418 419 512.1 512.2 519 521.1 523.1 524 525 526 527 530 531 602 603.0 701 702 703 706 710 711.1 712 713",
    l="101 102 103 104 104.2 104.3 105 106 107 108 201 201.3 201.4 202 202.2 215 301.4 302.2 302.3 304 305 306 307.2 309 410.4 415 416 416.1 501.2 502 502.1 503 504 505 506 507 508 508.1.1 508.4.1 508.2.1 508.3.1 509.0.1 509.0.2 510 511 511.1 511.9 512 513 514 515 516 517 518 520.1 520.3 521.4 522.2 523 528 529 532 532.1 601.1 601.3 705 707 708 709.1 709.2 711",
    a="113 114 201.2 206 208 209 210 211 212 213 214 301.1 301.3 302.1 302.5 307.1 308 310 401 402 402.1 403 404 404.1 405 406 406.1 407 408 408.1 408.2 409 410 410.1 410.2 410.3 411 412.1 413 413.1 414 414.1 501.1 520 520.2 521 521.3 522.1 601.2 601.4 709",
    c="301 301.2 302 307 412 501 502.2 508.1 508.2 508.3 508.4 509 511.2 521.2 522",
)
_ISSPROM_TYPES = _types(
    p="101.1 102.1 103.1 109 110 111 112 113.1 113.6 115 201.1 201.8 201.9 202.2 202.8 202.9 203 203.1 203.9 204 205 207 207.1 208.1 208.2 210.1 210.3 303 308.1 310.1 311 312 313 417 418 419 519 521.1 522.1 524 525 526 527 530 531 701 702 703 706 710.1 714.1",
    l="101 102 103 104 104.1 104.2 105 107 108 201 201.3 201.4 202 202.1 202.3 202.4 301.6 302.6 305 306 307.2 309 406.2 408.3 410.1 415 416 501.1 501.6 501.7 501.8 501.9 501.16 501.17 501.18 501.19 505.1 505.2 506 507 508 515.1.2 515.1.1 509.2 510 511 511.1 512 512.1 512.2 513.1 513.2 515 516 518 520.1 521.4 522.4 528 529 532.6 532.7 532.8 532.9 601 601.4 601.5 601.9 705 707 708 709.1 709.2 710.2 714.0.2",
    a="113 113.2 206 208 208.5 210 210.2 213 214 301.1 301.3 302.1 307.1 308 310 401 402 402.1 403 404 404.1 405 406 406.1 407 408 408.1 408.2 409 410 412.1 413 413.1 414 414.1 501.5 501.2 501.3 501.11 501.12 520 521.3 522.3 601.1 601.6 709 714.0.1",
    c="301 301.2 302 307 412 501 501.10 509.1 521 522 714",
)

# ---------------------------------------------------------------------------
# sym_key → číslo OOM symbolu. Co tu není, odvodí se z čísla v názvu
# (sym104 → "104", sym412a → "412"). None = cílová sada nemá ekvivalent;
# vrstva se exportuje jako unmapped_<klíč> bez CRT pravidla, takže v OOM
# zůstane vidět s importním symbolem a dá se přiřadit ručně.
# ---------------------------------------------------------------------------
_COMMON_OVERRIDES = {
    "sym216l": "415",     # historický název, ve skutečnosti 415
    "sym511P": None,      # stožáry jako body — OOM nemá bodový symbol
}

_ISOM_OVERRIDES = {
    **_COMMON_OVERRIDES,
    "sym203-1": "203.1",  # Rocky pit or cave (without entrance)
    "sym203-2": "203.2",  # Cave or rocky pit (with entrance)
    "sym408l": "410.4",   # liniová vegetace → Vegetation: fight, minimum width
    "sym501l": "505",     # OSM footway/pedestrian jako linie → Footpath
    "sym502DBa": "502.2", # dvouproudá silnice → Road with two carriageways
    "sym502DBb": "502.2",
    "sym523": "523.1",    # zřícenina jako bod → Ruin, minimum size
    "sym601": "601.1",    # Magnetic north line
    "sym603": "603.0",    # Spot height, dot
}

_ISSPROM_OVERRIDES = {
    **_COMMON_OVERRIDES,
    "sym105-2": "105",    # šablona nemá 105.2
    "sym203-1": "203",    # Rocky pit or cave (without a distinct entrance)
    "sym203-2": "203.1",  # Cave (with a distinct entrance)
    "sym209": "208.5",    # Dense boulder field
    "sym215a": "107",     # ISSprOM nemá 215 → Erosion gully or trench
    "sym215b": "107",
    "sym304": "305",      # ISSprOM nemá 304 → Small crossable watercourse
    "sym408l": "408.3",   # Vegetation: walk, minimum width
    "sym411": "410",      # Impassable vegetation
    "sym501-1": "501.1",  # Step or edge of paved area
    "sym501-2": "501.1",  # šablona nemá zvláštní symbol pro spodní úroveň
    "sym501-3": "501.3",  # Paved area with scattered trees
    "sym501l": "501.6",   # Paved area, footprint 1.4 m (linie)
    # Silnice 502–504 nejsou v ISSprOM — mapují se na liniové zpevněné plochy
    "sym502Da": "501.19", "sym502Db": "501.19", "sym502Dc": "501.19",
    "sym502DBa": "501.19", "sym502DBb": "501.19",
    "sym502a": "501.18", "sym502b": "501.18", "sym502Ba": "501.18", "sym502Bb": "501.18",
    "sym503": "501.8", "sym503Ba": "501.8", "sym503Bb": "501.8",
    "sym504": "505.2",    # Unpaved footpath or track, 2 m
    "sym505": "505.1",    # Unpaved footpath or track, 1.4 m
    "sym509a": "509.1", "sym509b": "509.1", "sym509Ba": "509.1", "sym509Bb": "509.1",
    "sym509-2": "509.2",  # Tramway
    "sym511a": "511",
    "sym512-1": "512",    # Bridge, one side (vstup pod most/do tunelu)
    "sym512-2": "512.2",  # Underpass or tunnel
    "sym512-3": None,     # 512.3 šablona nemá
    "sym513-1a": "513.1", "sym513-1b": "513.1",
    "sym513-2a": "513.2", "sym513-2b": "513.2",
    "sym522-1": "522.1",  # Pillar
    "sym523": None,       # ISSprOM nemá zříceninu
    "sym532a": "532.7", "sym532b": "532.7", "sym532c": "532.7",  # Stairway 2 m
    "sym533": None,
    "sym710-1": "710.1", "sym710-2": "710.2",
    "sym715": None,
}

# Bodová geometrie pro plošný/liniový symbol → bodová varianta "minimum size",
# pokud ji šablona má. Jinak jde do vrstvy isom_<číslo>_point bez CRT pravidla.
_POINT_FALLBACK = {
    "isom": {"201": "201.1", "202": "202.1", "208": "208.1", "210": "210.1",
             "113": "113.1", "308": "308.1", "310": "310.1", "512": "512.1",
             "521": "521.1", "523": "523.1"},
    "issprom": {"201": "201.1", "202": "202.2", "208": "208.1", "210": "210.1",
                "113": "113.1", "308": "308.1", "310": "310.1", "521": "521.1",
                "714": "714.1"},
}

_STANDARDS = {
    "isom": (_ISOM_TYPES, _ISOM_OVERRIDES),
    "issprom": (_ISSPROM_TYPES, _ISSPROM_OVERRIDES),
}

_UNMAPPED = object()


def standard_for_scale(scale) -> str:
    try:
        return "issprom" if int(scale) <= 5000 else "isom"
    except (TypeError, ValueError):
        return "isom"


def _default_code(sym_key: str) -> str | None:
    raw = sym_key[3:] if sym_key.startswith("sym") else sym_key
    m = re.match(r"^(\d+)", raw)
    return m.group(1) if m else None


def oom_code(sym_key: str, standard: str):
    """Vrátí (číslo, je_v_šabloně). Číslo je None jen když z klíče nejde
    odvodit vůbec nic."""
    types, overrides = _STANDARDS[standard]
    raw = sym_key[3:] if sym_key.startswith("sym") else sym_key
    if sym_key in overrides:
        code = overrides[sym_key]
        if code is None:
            return _default_code(sym_key), False
        return code, code in types
    # Vlastní ISOM vrstvy (klíč = název souboru, např. "501.1") — pokud
    # přesně odpovídá číslu v šabloně, použije se beze změny.
    if not sym_key.startswith("sym") and raw in types:
        return raw, True
    code = _default_code(sym_key)
    return code, (code in types) if code else False


def resolve_layer(sym_key: str, geom_kind: str, standard: str):
    """geom_kind: "Point" | "Line" | "Polygon".
    Vrátí (layer_name, action), action ∈ {"keep", "to_point"}; None pokud
    z klíče nejde odvodit číslo."""
    types, _ = _STANDARDS[standard]
    code, known = oom_code(sym_key, standard)
    if code is None:
        return None
    if not known:
        # Vlastní prefix, ať se nesrazí se skutečným číslem v šabloně
        # (např. 512.3 → "512" by jinak spadlo pod "Bridge, one side")
        raw = sym_key[3:] if sym_key.startswith("sym") else sym_key
        suffix = "_point" if geom_kind == "Point" else ""
        return f"unmapped_{raw}{suffix}", "keep"
    sym_type = types[code]
    if sym_type == "p":
        # Bodový symbol: linie/polygon se převede na reprezentativní bod
        return f"isom_{code}", ("keep" if geom_kind == "Point" else "to_point")
    # Liniový/plošný/kombinovaný symbol
    if geom_kind != "Point":
        return f"isom_{code}", "keep"
    fb = _POINT_FALLBACK[standard].get(code)
    if fb and types.get(fb) == "p":
        return f"isom_{fb}", "keep"
    # Bod bez bodové varianty — vlastní vrstva, CRT ji nepáruje
    return f"isom_{code}_point", "keep"


def write_crt(standard: str, path: str):
    """CRT pro OOM: každé číslo symbolu cílové sady ↔ vrstva isom_<číslo>.
    Liniové/plošné symboly navíc i pro varianty _line/_poly (vrstva se
    smíšenou geometrií se v exporteru rozdělí). Vrstvy isom_<číslo>_point
    u neliniových symbolů záměrně pravidlo nemají — OOM by bodu liniový
    symbol stejně nepřiřadil."""
    types, _ = _STANDARDS[standard]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for code, sym_type in types.items():
            f.write(f"{code}\tLayer = isom_{code}\n")
            if sym_type != "p":
                f.write(f"{code}\tLayer = isom_{code}_line\n")
                f.write(f"{code}\tLayer = isom_{code}_poly\n")
