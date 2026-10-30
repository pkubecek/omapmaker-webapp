"""
exporter.py — export výsledných vrstev do GeoPackage pro OpenOrienteering Mapper
a do lehkého GeoJSON balíčku pro klientský live náhled (výběr vrstev).
"""
import os
import re
import geopandas as gpd
import pandas as pd

from .oom_mapping import standard_for_scale, resolve_layer


def _oom_isom_code(sym_key: str) -> str | None:
    # Historicky pojmenované sym_keys, kde vedoucí číslo v NÁZVU symbolu
    # neodpovídá skutečnému ISOM/ISSprOM kódu prvku (viz komentáře v
    # symbols*.xml) - bez tohoto přepisu by GPKG export i CRT párování se
    # symboly v OOM dostaly špatný nebo neexistující kód:
    #  - sym216l: historický název ze symbols10/15.xml pro "216l", ve
    #    skutečnosti jde o ISOM 415 (Zřetelná hranice obdělávané půdy)
    #  - sym203-1 / sym203-2: obyčejný regex níže by z pomlčky "-1"/"-2"
    #    udělal jen "203" pro oba (ISOM ale rozlišuje 203.1 vs 203.2)
    overrides = {
        "sym216l": "415",
        "sym203-1": "203.1",
        "sym203-2": "203.2",
    }
    if sym_key in overrides:
        return overrides[sym_key]
    raw = sym_key[3:] if sym_key.startswith("sym") else sym_key
    m = re.match(r"^(\d+)", raw)
    return m.group(1) if m else None


def build_color_map(sym_library) -> dict:
    """Sestaví mapu {ISOM kód: hex barva} ze SymbolLibrary pro klientský
    live náhled (VectorPreview), ať odpovídá skutečným ISOM barvám místo
    hrubého odhadu podle skupiny.
    Priorita per symbol: color (linie) → facecolor (plocha/bod) → edgecolor.
    Pokud má kód víc sym_keys (např. 105-1a/105-1b), bere se první nalezená barva."""
    colors: dict = {}
    for sym_key, data in sym_library.items():
        code = _oom_isom_code(sym_key)
        if code is None or code in colors:
            continue
        props = data.get("props", {}) or {}
        color = props.get("color") or props.get("facecolor") or props.get("edgecolor")
        if color and color != "none":
            colors[code] = color
    return colors


class OomCollector:
    """Sbírá GeoDataFramy podle sym_keys pro pozdější export do GPKG.
    Nově navíc drží lehký paralelní store (`_geojson_rows`) pro GeoJSON
    preview na frontendu — nezávislý na GPKG logice, takže ji nijak nemění.

    GPKG vrstvy se jmenují podle čísla symbolu v cílové OOM sadě
    (ISOM 2017-2 / ISSprOM 2019 podle měřítka, viz oom_mapping.py), ne podle
    interního kódu — jinak se v OOM přes CRT nespárují. Každý prvek nese
    navíc sloupec `code` (kód z výběru vrstev), podle kterého se dá GPKG
    později vyfiltrovat (filter_gpkg)."""

    def __init__(self, current_crs: str = "EPSG:5514", scale=10_000):
        self._entries: list = []   # (sym_key, code, kind, GeoDataFrame)
        self._crs = current_crs
        self._standard = standard_for_scale(scale)
        self._geojson_rows: list = []

    def collect(self, sym_key: str, gdf: gpd.GeoDataFrame, group: str | None = None):
        if gdf is None or gdf.empty:
            return
        code = _oom_isom_code(sym_key)
        if code is None:
            return

        # --- GPKG store ---
        for kind, geom_types in [
            ("Point", ["Point", "MultiPoint"]),
            ("Line", ["LineString", "MultiLineString"]),
            ("Polygon", ["Polygon", "MultiPolygon"]),
        ]:
            mask = gdf.geometry.geom_type.isin(geom_types)
            subset = gdf.loc[mask, ["geometry"]].copy()
            if not subset.empty:
                self._entries.append((sym_key, code, kind, subset))

        # --- GeoJSON store (pro live náhled na klientu) ---
        self._geojson_rows.append({
            "sym_key": sym_key,
            "code": code,
            "group": group or "other",
            "geometry": gdf.geometry,
        })

    def export(self, output_path: str):
        if not self._entries:
            print("[exporter] Žádné vrstvy k exportu.")
            return

        if os.path.exists(output_path):
            os.remove(output_path)

        # 1) sym_key → název vrstvy v cílové OOM sadě (+ případný převod na bod)
        groups: dict = {}   # base_name -> {kind: [frames]}
        for sym_key, code, kind, subset in self._entries:
            resolved = resolve_layer(sym_key, kind, self._standard)
            if resolved is None:
                continue
            base_name, action = resolved
            frame = subset.copy()
            if action == "to_point":
                frame["geometry"] = frame.geometry.representative_point()
                kind = "Point"
            frame["code"] = code
            groups.setdefault(base_name, {}).setdefault(kind, []).append(frame)

        # 2) zápis — vrstva se smíšenou geometrií se rozdělí příponou
        #    (_line/_poly/_point); CRT páruje i tyhle varianty
        SUFFIX = {"Point": "_point", "Line": "_line", "Polygon": "_poly"}
        written = 0
        for base_name in sorted(groups):
            kinds = groups[base_name]
            use_suffix = len(kinds) > 1
            for kind, frames in kinds.items():
                layer_name = f"{base_name}{SUFFIX[kind] if use_suffix else ''}"
                try:
                    merged = gpd.GeoDataFrame(
                        pd.concat(frames, ignore_index=True), crs=self._crs
                    )
                    merged = merged[merged.geometry.notna() & ~merged.geometry.is_empty]
                    if merged.empty:
                        continue
                    if kind == "Polygon":
                        merged.geometry = merged.geometry.buffer(0)
                        merged = merged[merged.geometry.is_valid & ~merged.geometry.is_empty]
                        if merged.empty:
                            continue
                    merged = merged.drop_duplicates(subset=["geometry"])
                    merged = merged[["code", "geometry"]].copy()
                    merged["Layer"] = layer_name
                    merged.to_file(output_path, layer=layer_name, driver="GPKG")
                    print(f"[exporter] {layer_name}: {len(merged)} prvků [{kind}]")
                    written += 1
                except Exception as e:
                    print(f"[exporter] Chyba {layer_name} [{kind}]: {e}")

        print(f"[exporter] GPKG export ({self._standard}): {written} vrstev → {output_path}")

    def export_geojson(self, output_path: str, simplify_tolerance: float | None = None):
        """
        Uloží lehký GeoJSON se všemi sesbíranými prvky, properties =
        {code, sym_key, group}. Souřadnice zůstávají v `self._crs` (bez
        reprojekce do WGS84) — frontend je jen škáluje do SVG viewBoxu pro
        schematický náhled, nekreslí je nad podkladovou mapou.

        `simplify_tolerance` (v metrech) — vyplatí se pro těžké LiDAR vrstvy
        (vrstevnice, mikroreliéf), ať GeoJSON zůstane rozumně malý; na PNG/GPKG
        export to nemá vliv, ty jedou z plné geometrie.
        """
        if not self._geojson_rows:
            print("[exporter] Žádná data pro GeoJSON export.")
            return None

        frames = []
        for row in self._geojson_rows:
            geom = row["geometry"]
            if simplify_tolerance:
                geom = geom.simplify(simplify_tolerance, preserve_topology=True)
            gdf = gpd.GeoDataFrame(
                {"code": row["code"], "sym_key": row["sym_key"], "group": row["group"]},
                geometry=geom, crs=self._crs, index=geom.index,
            )
            frames.append(gdf)

        merged = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=self._crs)
        merged = merged[merged.geometry.notna() & ~merged.geometry.is_empty]
        if os.path.exists(output_path):
            os.remove(output_path)
        merged.to_file(output_path, driver="GeoJSON", COORDINATE_PRECISION=2)
        print(f"[exporter] GeoJSON preview export: {len(merged)} prvků → {output_path}")
        return output_path


def export_gpkg(layers: dict, output_path: str, current_crs: str = "EPSG:5514",
                scale=10_000):
    """Zkrácená verze pro přímé volání s dict {sym_key: GeoDataFrame}."""
    collector = OomCollector(current_crs, scale=scale)
    for sym_key, gdf in layers.items():
        collector.collect(sym_key, gdf)
    collector.export(output_path)


def filter_gpkg(src_path: str, dst_path: str, codes) -> int:
    """Zkopíruje z plného GPKG jen prvky, jejichž `code` je ve výběru
    vrstev (stejné kódy jako LayerSelector / selected_codes). Vrátí počet
    zapsaných vrstev."""
    try:
        import pyogrio
        layer_names = [name for name, _ in pyogrio.list_layers(src_path)]
    except ImportError:
        import fiona
        layer_names = fiona.listlayers(src_path)

    codes = {str(c) for c in codes}
    if os.path.exists(dst_path):
        os.remove(dst_path)
    written = 0
    for layer_name in layer_names:
        gdf = gpd.read_file(src_path, layer=layer_name)
        if "code" not in gdf.columns:
            continue
        gdf = gdf[gdf["code"].astype(str).isin(codes)]
        if gdf.empty:
            continue
        gdf.to_file(dst_path, layer=layer_name, driver="GPKG")
        written += 1
    return written
