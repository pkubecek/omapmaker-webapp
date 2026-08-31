"""
exporter.py — export výsledných vrstev do GeoPackage pro OpenOrienteering Mapper
a do lehkého GeoJSON balíčku pro klientský live náhled (výběr vrstev).
"""
import os
import re
import geopandas as gpd
import pandas as pd


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
    """Sbírá GeoDataFramy podle ISOM kódů pro pozdější export do GPKG.
    Nově navíc drží lehký paralelní store (`_geojson_rows`) pro GeoJSON
    preview na frontendu — nezávislý na GPKG logice, takže ji nijak nemění."""

    def __init__(self, current_crs: str = "EPSG:5514"):
        self._layers: dict = {}
        self._crs = current_crs
        self._geojson_rows: list = []

    def collect(self, sym_key: str, gdf: gpd.GeoDataFrame, group: str | None = None):
        if gdf is None or gdf.empty:
            return
        code = _oom_isom_code(sym_key)
        if code is None:
            return

        # --- GPKG store (beze změny chování) ---
        if code not in self._layers:
            self._layers[code] = {"Point": [], "Line": [], "Polygon": []}
        for geom_type, geom_types in [
            ("Point", ["Point", "MultiPoint"]),
            ("Line", ["LineString", "MultiLineString"]),
            ("Polygon", ["Polygon", "MultiPolygon"]),
        ]:
            mask = gdf.geometry.geom_type.isin(geom_types)
            subset = gdf.loc[mask, ["geometry"]].copy()
            if not subset.empty:
                self._layers[code][geom_type].append(subset)

        # --- GeoJSON store (pro live náhled na klientu) ---
        self._geojson_rows.append({
            "sym_key": sym_key,
            "code": code,
            "group": group or "other",
            "geometry": gdf.geometry,
        })

    def export(self, output_path: str):
        if not self._layers:
            print("[exporter] Žádné vrstvy k exportu.")
            return

        if os.path.exists(output_path):
            os.remove(output_path)

        SUFFIX = {"Point": "_point", "Line": "_line", "Polygon": "_poly"}
        written = 0

        for code in sorted(self._layers.keys(), key=lambda x: float(x)):
            buckets = self._layers[code]
            non_empty = {k: v for k, v in buckets.items() if v}
            if not non_empty:
                continue
            use_suffix = len(non_empty) > 1

            for geom_type, frames in non_empty.items():
                try:
                    merged = gpd.GeoDataFrame(
                        pd.concat(frames, ignore_index=True), crs=self._crs
                    )
                    merged = merged[merged.geometry.notna() & ~merged.geometry.is_empty]
                    if merged.empty:
                        continue
                    if geom_type == "Polygon":
                        merged.geometry = merged.geometry.buffer(0)
                        merged = merged[merged.geometry.is_valid & ~merged.geometry.is_empty]
                        if merged.empty:
                            continue
                    merged = merged.drop_duplicates(subset=["geometry"])
                    layer_name = f"isom_{code}{SUFFIX[geom_type] if use_suffix else ''}"
                    merged = merged[["geometry"]].copy()
                    merged["Layer"] = layer_name
                    merged.to_file(output_path, layer=layer_name, driver="GPKG")
                    print(f"[exporter] {layer_name}: {len(merged)} prvků [{geom_type}]")
                    written += 1
                except Exception as e:
                    print(f"[exporter] Chyba isom_{code} [{geom_type}]: {e}")

        print(f"[exporter] GPKG export: {written} vrstev → {output_path}")

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


def export_gpkg(layers: dict, output_path: str, current_crs: str = "EPSG:5514"):
    """Zkrácená verze pro přímé volání s dict {sym_key: GeoDataFrame}."""
    collector = OomCollector(current_crs)
    for sym_key, gdf in layers.items():
        collector.collect(sym_key, gdf)
    collector.export(output_path)