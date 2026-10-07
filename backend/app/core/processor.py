"""
processor.py — zpracování bodových mračen, interpolace DTM/DSM,
klasifikace vegetace, vektorizace skal, terénní mikrotvary.
Přepsáno z OMapMaker_v7.py bez tkinter závislostí.
"""
import os
import tempfile
import numpy as np
import laspy
import rasterio
import rasterio.features
import rasterio.transform
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from scipy.interpolate import griddata
from scipy.ndimage import (
    binary_dilation, binary_erosion, gaussian_filter, label,
    find_objects, minimum_filter, binary_opening, binary_closing,
)
from shapely.geometry import MultiPoint, Point, Polygon, MultiPolygon, shape
from shapely.ops import unary_union
import geopandas as gpd
from pyproj import CRS, Transformer


# ---------------------------------------------------------------------------
# DTM (DMR) loading
# ---------------------------------------------------------------------------

def load_dmr_grid(dmr_path: str, target_crs_code: str,
                  pixel_size: float = 0.5, sigma_smooth: float = 4,
                  bbox_clip: tuple | None = None,
                  progress_cb=None) -> tuple:
    """
    Načte bodové mračno DTM (.las/.laz), interpoluje na pravidelnou mřížku.
    bbox_clip: (minx, maxx, miny, maxy) pro ořez na dlaždici
    Vrací: (dmr_grid_cubic, grid_x, grid_y, extent, points, z)
    """
    def _cb(msg):
        print(f"[processor] {msg}")
        if progress_cb:
            progress_cb(msg)

    _cb(f"Načítám DTM: {os.path.basename(dmr_path)}")
    MAX_POINTS = 2_500_000
    xs, ys, zs = [], [], []
    transformer = None

    with laspy.open(dmr_path) as fh:
        try:
            source_crs = fh.header.parse_crs()
            if source_crs is None:
                raise ValueError("No CRS")
        except Exception:
            source_crs = CRS.from_epsg(5514)

        # Detekce CRS z rozsahu souřadnic — GUGiK LAZ nemá CRS v headeru
        # EPSG:5514 má záporné souřadnice; EPSG:2180 má kladné ~140k-900k
        hdr = fh.header
        x_min = float(hdr.x_min)
        if source_crs.equals(CRS.from_epsg(5514)) and x_min > 0:
            source_crs = CRS.from_epsg(2180)

        try:
            target_crs_obj = CRS.from_string(target_crs_code)
            if source_crs != target_crs_obj:
                transformer = Transformer.from_crs(source_crs, target_crs_obj, always_xy=True)
        except Exception as e:
            print(f"[processor] Varování transformace DTM: {e}")

        total_points = fh.header.point_count
        fraction = min(1.0, MAX_POINTS / total_points) if total_points > 0 else 1.0

        # Automatická detekce záměny os (cx/cy) — udělá se JEDNOU za celý
        # soubor, ale outcome-based: vyzkouší se obě orientace přímo proti
        # bboxu dlaždice a vybere ta, co dá víc bodů uvnitř. Porovnávání
        # vzdálenosti bodu od středu eastingu/northingu (starší přístup) je
        # nespolehlivé tam, kde jsou tyhle středy číselně blízko sebe —
        # typicky blízko státní hranice — kde je to skoro hod mincí.
        cx_is_easting = None
        if bbox_clip is not None:
            bx0, bx1, by0, by1 = bbox_clip

        for chunk in fh.chunk_iterator(1_000_000):
            clas = np.array(chunk.classification)
            ground_mask = (clas == 2) | (clas == 8)
            if not np.any(ground_mask):
                continue
            cx = np.array(chunk.x[ground_mask])
            cy = np.array(chunk.y[ground_mask])
            cz = np.array(chunk.z[ground_mask])
            if fraction < 1.0:
                rnd = np.random.rand(len(cx)) < fraction
                cx, cy, cz = cx[rnd], cy[rnd], cz[rnd]
            if len(cx) == 0:
                continue
            if transformer:
                cx, cy = transformer.transform(cx, cy)
            # Ořez na bbox dlaždice
            if bbox_clip is not None:
                if cx_is_easting is None:
                    n_sample = min(20_000, len(cx))
                    sx, sy = cx[:n_sample], cy[:n_sample]
                    hits_normal = int(np.sum(
                        (sx >= bx0) & (sx <= bx1) & (sy >= by0) & (sy <= by1)))
                    hits_swapped = int(np.sum(
                        (sy >= bx0) & (sy <= bx1) & (sx >= by0) & (sx <= by1)))
                    if hits_normal == 0 and hits_swapped == 0:
                        cx_is_easting = True  # ani jedna varianta netrefila vzorek, defaultuj
                    else:
                        cx_is_easting = hits_normal >= hits_swapped
                    _cb(f"Detekce os dlaždice: chunk.x="
                        f"{'easting' if cx_is_easting else 'northing'} "
                        f"(shod: normal={hits_normal}, swapped={hits_swapped})")
                if cx_is_easting:
                    m = (cx >= bx0) & (cx <= bx1) & (cy >= by0) & (cy <= by1)
                else:
                    m = (cx >= by0) & (cx <= by1) & (cy >= bx0) & (cy <= bx1)
                cx, cy, cz = cx[m], cy[m], cz[m]
                if not cx_is_easting:
                    # Zdroj měl osy prohozené (chunk.x=northing, chunk.y=easting) —
                    # filtr už to zohlednil, ale bez tohohle swapu by se northing
                    # uložilo jako "x" a easting jako "y" a celá navazující mřížka
                    # (grid_x/grid_y, clip_polygon, vrstevnice...) by pak byla vůči
                    # zbytku pipeline (core_box aj., vždy v pořadí E,N) prohozená.
                    cx, cy = cy, cx
            if len(cx) == 0:
                continue
            xs.append(cx)
            ys.append(cy)
            zs.append(cz)

    if not xs:
        raise ValueError("DTM neobsahuje žádné body klasifikované jako terén (třídy 2, 8).")

    x = np.concatenate(xs)
    y = np.concatenate(ys)
    z = np.concatenate(zs)
    _cb(f"DTM načteno: {len(x):,} bodů")

    buffer_dist = pixel_size
    min_x, max_x = x.min() - buffer_dist, x.max() + buffer_dist
    min_y, max_y = y.min() - buffer_dist, y.max() + buffer_dist
    extent = (min_x, max_x, min_y, max_y)

    grid_x, grid_y = np.mgrid[min_x:max_x:pixel_size, min_y:max_y:pixel_size]

    _cb("Interpoluji DTM (cubic)...")
    points = np.vstack((x, y)).T
    valid = np.isfinite(points).all(axis=1) & np.isfinite(z)
    points = points[valid]
    z = z[valid]

    shift_x = np.mean(points[:, 0])
    shift_y = np.mean(points[:, 1])
    pts_shifted = points - np.array([shift_x, shift_y])
    gx_shifted = grid_x - shift_x
    gy_shifted = grid_y - shift_y

    dmr_grid = griddata(pts_shifted, z, (gx_shifted, gy_shifted), method="cubic")
    mask_nan = np.isnan(dmr_grid)
    if np.any(mask_nan):
        dmr_grid_nearest = griddata(pts_shifted, z, (gx_shifted, gy_shifted), method="nearest")
        dmr_grid[mask_nan] = dmr_grid_nearest[mask_nan]
    dmr_grid = gaussian_filter(dmr_grid, sigma=sigma_smooth)

    return dmr_grid, grid_x, grid_y, extent, points, z


# ---------------------------------------------------------------------------
# Jednorázové načtení LAZ pro všechny dlaždice (místo čtení celého souboru
# znovu pro každou dlaždici). Body se během jediného průchodu rozdělí do
# dočasných binárních souborů po dlaždicích (float64 x,y,z) — v RAM se
# nedrží celé mračno, jen jeden chunk.
# ---------------------------------------------------------------------------

# Stejné ředění jako dřív v load_dmr_grid/load_dmp_grid: podíl se počítá
# z počtu bodů CELÉHO souboru (max ~2,5 M bodů ze souboru). Výsledky tak
# zůstávají srovnatelné s předchozí verzí; zvýšení hustoty je samostatné
# rozhodnutí kvalita × čas.
MAX_POINTS = 2_500_000


def _source_crs_of(fh):
    """CRS z hlavičky LAZ; GUGiK LAZ CRS nemá → detekce z rozsahu souřadnic."""
    try:
        source_crs = fh.header.parse_crs()
        if source_crs is None:
            raise ValueError("No CRS")
    except Exception:
        source_crs = CRS.from_epsg(5514)
    # EPSG:5514 má záporné souřadnice; EPSG:2180 kladné ~140k-900k
    if source_crs.equals(CRS.from_epsg(5514)) and float(fh.header.x_min) > 0:
        source_crs = CRS.from_epsg(2180)
    return source_crs


def split_points_to_tiles(laz_path: str, target_crs_code: str, tile_boxes: list,
                          out_dir: str, kind: str = "dtm", margin: float = 0.0,
                          max_points: int = MAX_POINTS,
                          progress_cb=None) -> list:
    """
    Přečte LAZ JEDNOU a body rozdělí do souborů po dlaždicích.

    kind: "dtm" → jen terén (třídy 2, 8); "dsm" → vše kromě šumu (třída 7)
    tile_boxes: [(x0, x1, y0, y1), ...] v cílovém CRS (bbox dlaždice vč. překryvu)
    margin: rozšíření bboxu dlaždice (m) — u DSM, ať interpolace nemá díry u okraje
    Vrací seznam cest (jedna na dlaždici) k souborům s float64 trojicemi x,y,z.

    Ředění bodů: fraction = max_points / počet bodů v souboru (jako dřív).
    """
    def _cb(msg):
        print(f"[processor] {msg}")
        if progress_cb:
            progress_cb(msg)

    os.makedirs(out_dir, exist_ok=True)
    boxes = [(x0 - margin, x1 + margin, y0 - margin, y1 + margin) for (x0, x1, y0, y1) in tile_boxes]
    paths = [os.path.join(out_dir, f"{kind}_{i}.bin") for i in range(len(boxes))]
    files = [open(p, "wb") for p in paths]
    counts = [0] * len(boxes)

    gx0 = min(b[0] for b in boxes); gx1 = max(b[1] for b in boxes)
    gy0 = min(b[2] for b in boxes); gy1 = max(b[3] for b in boxes)

    try:
        with laspy.open(laz_path) as fh:
            source_crs = _source_crs_of(fh)
            transformer = None
            try:
                target_crs_obj = CRS.from_string(target_crs_code)
                if source_crs != target_crs_obj:
                    transformer = Transformer.from_crs(source_crs, target_crs_obj, always_xy=True)
            except Exception as e:
                print(f"[processor] Varování transformace {kind}: {e}")

            hdr = fh.header
            total_points = hdr.point_count
            fraction = min(1.0, max_points / total_points) if total_points > 0 else 1.0
            _cb(f"{kind.upper()}: {total_points:,} bodů v souboru, ředění {fraction:.2f}")
            cx_is_easting = None   # detekce prohozených os (outcome-based, jednou za soubor)

            for chunk in fh.chunk_iterator(1_000_000):
                clas = np.array(chunk.classification)
                keep = ((clas == 2) | (clas == 8)) if kind == "dtm" else (clas != 7)
                n_keep = int(np.count_nonzero(keep))
                if n_keep == 0:
                    continue

                cx = np.array(chunk.x[keep])
                cy = np.array(chunk.y[keep])
                cz = np.array(chunk.z[keep])
                if fraction < 1.0:
                    rnd = np.random.rand(len(cx)) < fraction
                    cx, cy, cz = cx[rnd], cy[rnd], cz[rnd]
                if len(cx) == 0:
                    continue
                if transformer:
                    cx, cy = transformer.transform(cx, cy)

                if cx_is_easting is None:
                    n_sample = min(20_000, len(cx))
                    sx, sy = cx[:n_sample], cy[:n_sample]
                    hits_normal = int(np.sum((sx >= gx0) & (sx <= gx1) & (sy >= gy0) & (sy <= gy1)))
                    hits_swapped = int(np.sum((sy >= gx0) & (sy <= gx1) & (sx >= gy0) & (sx <= gy1)))
                    cx_is_easting = True if (hits_normal == 0 and hits_swapped == 0) else hits_normal >= hits_swapped
                    _cb(f"Detekce os {kind.upper()}: chunk.x={'easting' if cx_is_easting else 'northing'} "
                        f"(shod: normal={hits_normal}, swapped={hits_swapped})")
                if not cx_is_easting:
                    cx, cy = cy, cx

                for i, (bx0, bx1, by0, by1) in enumerate(boxes):
                    m = (cx >= bx0) & (cx <= bx1) & (cy >= by0) & (cy <= by1)
                    k = int(np.count_nonzero(m))
                    if k:
                        files[i].write(np.column_stack((cx[m], cy[m], cz[m])).astype(np.float64).tobytes())
                        counts[i] += k
    finally:
        for f in files:
            f.close()

    _cb(f"{kind.upper()} načteno jednou pro {len(boxes)} dlaždic: {sum(counts):,} bodů")
    return paths


def read_tile_points(path: str) -> np.ndarray:
    """Načte body dlaždice (N×3 float64). Prázdný/neexistující soubor → (0,3)."""
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        return np.empty((0, 3))
    return np.fromfile(path, dtype=np.float64).reshape(-1, 3)


def _grid_axes(min_x, max_x, min_y, max_y, pixel_size):
    """
    Mřížka jako v np.mgrid[min_x:max_x:pixel_size, min_y:max_y:pixel_size],
    ale grid_x/grid_y jsou jen broadcast POHLEDY (bez alokace 2× ~100 MB).
    Pro čtení (.shape, .min(), indexace, aritmetika) se chovají jako plné pole.
    """
    xs = np.mgrid[min_x:max_x:pixel_size]
    ys = np.mgrid[min_y:max_y:pixel_size]
    shape = (len(xs), len(ys))
    grid_x = np.broadcast_to(xs[:, None], shape)
    grid_y = np.broadcast_to(ys[None, :], shape)
    return grid_x, grid_y, xs, ys


def _eval_blocks(interp, xs_shifted, ys_shifted, block_rows=256):
    """Vyhodnotí interpolátor po pásech řádků — bez obřího pole souřadnic všech pixelů."""
    out = np.empty((len(xs_shifted), len(ys_shifted)), dtype=np.float64)
    for i0 in range(0, len(xs_shifted), block_rows):
        i1 = min(i0 + block_rows, len(xs_shifted))
        gx = np.broadcast_to(xs_shifted[i0:i1, None], (i1 - i0, len(ys_shifted)))
        gy = np.broadcast_to(ys_shifted[None, :], (i1 - i0, len(ys_shifted)))
        out[i0:i1] = interp(gx, gy)
    return out


def dtm_grids_from_points(pts_xyz: np.ndarray, pixel_size: float = 0.5,
                          sigma_smooth: float = 4, progress_cb=None) -> tuple:
    """
    Stejný výsledek jako load_dmr_grid() + lineární DTM z _process_tile(),
    ale s JEDNOU Delaunayovou triangulací sdílenou pro kubickou i lineární
    interpolaci (dřív se stejná triangulace stavěla dvakrát).

    Vrací: (dmr_grid_cubic_smoothed, dmr_grid_linear, grid_x, grid_y, extent, points, z)
    """
    from scipy.spatial import Delaunay
    from scipy.interpolate import CloughTocher2DInterpolator, LinearNDInterpolator, NearestNDInterpolator

    def _cb(msg):
        print(f"[processor] {msg}")
        if progress_cb:
            progress_cb(msg)

    if len(pts_xyz) == 0:
        raise ValueError("DTM neobsahuje žádné body klasifikované jako terén (třídy 2, 8).")

    x, y, z = pts_xyz[:, 0], pts_xyz[:, 1], pts_xyz[:, 2]
    _cb(f"DTM dlaždice: {len(x):,} bodů")

    buffer_dist = pixel_size
    min_x, max_x = x.min() - buffer_dist, x.max() + buffer_dist
    min_y, max_y = y.min() - buffer_dist, y.max() + buffer_dist
    extent = (min_x, max_x, min_y, max_y)
    grid_x, grid_y, xs, ys = _grid_axes(min_x, max_x, min_y, max_y, pixel_size)

    points = np.vstack((x, y)).T
    valid = np.isfinite(points).all(axis=1) & np.isfinite(z)
    points = points[valid]
    z = z[valid]

    shift_x = np.mean(points[:, 0])
    shift_y = np.mean(points[:, 1])
    pts_shifted = points - np.array([shift_x, shift_y])
    xs_sh, ys_sh = xs - shift_x, ys - shift_y

    _cb("Triangulace DTM (jednou pro cubic i linear)...")
    tri = Delaunay(pts_shifted)

    _cb("Interpoluji DTM (cubic)...")
    dmr_grid = _eval_blocks(CloughTocher2DInterpolator(tri, z), xs_sh, ys_sh)
    mask_nan = np.isnan(dmr_grid)
    if np.any(mask_nan):
        # Nearest jen pro chybějící pixely (dřív se počítal pro celý grid)
        ii, jj = np.nonzero(mask_nan)
        dmr_grid[mask_nan] = NearestNDInterpolator(pts_shifted, z)(xs_sh[ii], ys_sh[jj])
    dmr_grid = gaussian_filter(dmr_grid, sigma=sigma_smooth)

    _cb("Interpoluji DTM (linear)...")
    dmr_linear = _eval_blocks(LinearNDInterpolator(tri, z), xs_sh, ys_sh)
    del tri
    if np.isnan(dmr_linear).all():
        dmr_linear = _eval_blocks(NearestNDInterpolator(pts_shifted, z), xs_sh, ys_sh)

    return dmr_grid, dmr_linear, grid_x, grid_y, extent, points, z


def dsm_grid_from_points(pts_xyz: np.ndarray, grid_x: np.ndarray, grid_y: np.ndarray) -> np.ndarray:
    """Lineární interpolace DSM bodů DLAŽDICE na mřížku DTM (dřív body celého souboru)."""
    from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator

    if len(pts_xyz) == 0:
        raise ValueError("DSM neobsahuje platná data.")
    pts = pts_xyz[:, :2]
    z = pts_xyz[:, 2]
    valid = np.isfinite(pts).all(axis=1) & np.isfinite(z)
    pts, z = pts[valid], z[valid]

    xs = grid_x[:, 0]
    ys = grid_y[0, :]
    shift_x, shift_y = np.mean(pts[:, 0]), np.mean(pts[:, 1])
    pts_shifted = pts - np.array([shift_x, shift_y])
    xs_sh, ys_sh = xs - shift_x, ys - shift_y

    dmp_grid = _eval_blocks(LinearNDInterpolator(pts_shifted, z), xs_sh, ys_sh)
    if np.isnan(dmp_grid).all():
        dmp_grid = _eval_blocks(NearestNDInterpolator(pts_shifted, z), xs_sh, ys_sh)
    return dmp_grid


# ---------------------------------------------------------------------------
# DSM (DMP) loading
# ---------------------------------------------------------------------------

def load_dmp_grid(dmp_path: str, grid_x: np.ndarray, grid_y: np.ndarray,
                  extent: tuple, target_crs_code: str,
                  progress_cb=None) -> np.ndarray:
    """Načte DSM (.las/.laz nebo .tif) a interpoluje na stejnou mřížku jako DTM."""
    def _cb(msg):
        print(f"[processor] {msg}")
        if progress_cb:
            progress_cb(msg)

    _cb(f"Načítám DSM: {os.path.basename(dmp_path)}")
    MAX_POINTS = 2_500_000
    ext = os.path.splitext(dmp_path)[1].lower()

    if ext in (".las", ".laz"):
        xs, ys, zs = [], [], []
        transformer = None
        with laspy.open(dmp_path) as fh:
            try:
                source_crs = fh.header.parse_crs()
                if source_crs is None:
                    source_crs = CRS.from_epsg(5514)
            except Exception:
                source_crs = CRS.from_epsg(5514)

            # Detekce CRS z souřadnic
            if source_crs.equals(CRS.from_epsg(5514)) and float(fh.header.x_min) > 0:
                source_crs = CRS.from_epsg(2180)

            try:
                target_crs_obj = CRS.from_string(target_crs_code)
                if source_crs != target_crs_obj:
                    transformer = Transformer.from_crs(source_crs, target_crs_obj, always_xy=True)
            except Exception:
                pass

            total = fh.header.point_count
            fraction = min(1.0, MAX_POINTS / total) if total > 0 else 1.0

            for chunk in fh.chunk_iterator(500_000):
                cx = np.array(chunk.x)
                cy = np.array(chunk.y)
                cz = np.array(chunk.z)
                cc = np.array(chunk.classification)
                valid_mask = cc != 7
                if fraction < 1.0:
                    valid_mask &= np.random.rand(len(cx)) < fraction
                if np.any(valid_mask):
                    cx, cy, cz = cx[valid_mask], cy[valid_mask], cz[valid_mask]
                    if transformer:
                        cx, cy = transformer.transform(cx, cy)
                    xs.append(cx)
                    ys.append(cy)
                    zs.append(cz)

        if not xs:
            raise ValueError("DSM neobsahuje platná data.")

        x = np.concatenate(xs)
        y = np.concatenate(ys)
        z = np.concatenate(zs)
        pts = np.vstack((x, y)).T
        valid = np.isfinite(pts).all(axis=1) & np.isfinite(z)
        pts, z = pts[valid], z[valid]

    elif ext in (".tif", ".tiff"):
        with rasterio.open(dmp_path) as src:
            total_px = src.width * src.height
            if total_px > MAX_POINTS:
                scale = (MAX_POINTS / total_px) ** 0.5
                nw, nh = int(src.width * scale), int(src.height * scale)
                data = src.read(1, out_shape=(nh, nw), resampling=Resampling.bilinear)
                transform = src.transform * src.transform.scale(src.width / nw, src.height / nh)
            else:
                data = src.read(1)
                transform = src.transform
            rows, cols = np.indices(data.shape)
            xs2, ys2 = rasterio.transform.xy(transform, rows.flatten(), cols.flatten())
            z = data.flatten()
            if src.nodata is not None:
                mask = z != src.nodata
                x, y = np.array(xs2)[mask], np.array(ys2)[mask]
                z = z[mask]
            else:
                x, y = np.array(xs2), np.array(ys2)
        pts = np.vstack((x, y)).T
        valid = np.isfinite(pts).all(axis=1) & np.isfinite(z)
        pts, z = pts[valid], z[valid]
    else:
        raise ValueError(f"Nepodporovaný formát DSM: {ext}")

    _cb("Interpoluji DSM...")
    shift_x = np.mean(pts[:, 0])
    shift_y = np.mean(pts[:, 1])
    pts_shifted = pts - np.array([shift_x, shift_y])
    gx_shifted = grid_x - shift_x
    gy_shifted = grid_y - shift_y

    dmp_grid = griddata(pts_shifted, z, (gx_shifted, gy_shifted), method="linear")
    if np.isnan(dmp_grid).all():
        dmp_grid = griddata(pts_shifted, z, (gx_shifted, gy_shifted), method="nearest")

    return dmp_grid


# ---------------------------------------------------------------------------
# Vegetation classification
# ---------------------------------------------------------------------------

def _chaikin_ring(coords: np.ndarray, iterations: int = 4) -> np.ndarray:
    """
    Chaikinovo ořezávání rohů na uzavřeném kruhu souřadnic.
    Každou hranu v každé iteraci nahradí dvěma body (25 % a 75 % podél hrany) —
    limitně se blíží hladké (kvadratické B-spline) křivce bez ostrých rohů.
    """
    coords = np.asarray(coords, dtype=float)
    if len(coords) >= 2 and np.allclose(coords[0], coords[-1]):
        coords = coords[:-1]
    if len(coords) < 3:
        return np.vstack([coords, coords[0]]) if len(coords) else coords
    for _ in range(iterations):
        n = len(coords)
        new_pts = np.empty((n * 2, 2))
        p0 = coords
        p1 = np.roll(coords, -1, axis=0)
        new_pts[0::2] = 0.75 * p0 + 0.25 * p1
        new_pts[1::2] = 0.25 * p0 + 0.75 * p1
        coords = new_pts
    return np.vstack([coords, coords[0]])


def _chaikin_smooth_geom(geom, iterations: int = 4):
    """Aplikuje Chaikinovo vyhlazení na exterior i interior kruhy Polygonu/MultiPolygonu."""
    if geom is None or geom.is_empty:
        return geom

    def _smooth_poly(poly):
        try:
            ext = _chaikin_ring(np.asarray(poly.exterior.coords), iterations)
            ints = [_chaikin_ring(np.asarray(r.coords), iterations) for r in poly.interiors]
            new_poly = Polygon(ext, ints)
            return new_poly if new_poly.is_valid else new_poly.buffer(0)
        except Exception:
            return poly

    if geom.geom_type == "Polygon":
        return _smooth_poly(geom)
    elif geom.geom_type == "MultiPolygon":
        return MultiPolygon([_smooth_poly(p) for p in geom.geoms if not p.is_empty])
    return geom


def classify_vegetation(vegetation_height: np.ndarray, bins: list,
                         transform, dmr_path: str,
                         progress_cb=None) -> gpd.GeoDataFrame:
    """
    Klasifikuje výšku vegetace do tříd a vektorizuje polygony.
    bins: [b1, b2, b3, b4] — hranice výšek v metrech
    """
    def _cb(msg):
        print(f"[processor] {msg}")
        if progress_cb:
            progress_cb(msg)

    _cb("Klasifikuji vegetaci...")
    full_bins = [-1, 0] + list(bins)
    class_names = {
        1: "Paseka", 2: "Louka", 3: "Nizky_porost",
        4: "Stredni_porost", 5: "Vysoky_porost", 6: "Les",
    }

    classified_raster_raw = np.digitize(
        np.nan_to_num(vegetation_height, nan=-9999), full_bins
    ).astype(np.int32)

    cleaned = classified_raster_raw.copy()
    struct = np.ones((3, 3), dtype=bool)
    for c in np.unique(cleaned):
        if c == 0:
            continue
        mask = cleaned == c
        mask = binary_opening(mask, structure=struct)
        mask = binary_closing(mask, structure=struct)
        cleaned[cleaned == c] = 0
        cleaned[mask] = c

    classified_raster = np.flipud(cleaned.T)
    pixel_area = abs(transform.a * transform.e)
    min_area = 50 * pixel_area
    mask = classified_raster != 0

    try:
        results = rasterio.features.shapes(classified_raster, mask=mask, transform=transform)
        features = []
        for geom, value in results:
            class_id = int(value)
            if class_id == 0:
                continue
            features.append({
                "geometry": shape(geom),
                "class_id": class_id,
                "class_name": class_names.get(class_id, "Neznama"),
            })
        if not features:
            return gpd.GeoDataFrame(columns=["class_name", "class_id", "geometry"])

        gdf = gpd.GeoDataFrame(features)
        gdf = gdf[gdf.geometry.area >= min_area]
        gdf.geometry = gdf.geometry.simplify(0.5, preserve_topology=True)
        dissolved = gdf.dissolve(by="class_name", aggfunc="first").reset_index()

        # Zaoblení hran — rastrová vektorizace dává "schodovité" polygony.
        # Dilatace + eroze se zaoblenými rohy (round join) hrany vyhladí a zakulatí,
        # aniž by se polygon výrazně zvětšil nebo zmenšil.
        SMOOTH_DIST = 3.0  # metry — vyšší = kulatější, ale méně přesné hranice
        dissolved.geometry = (
            dissolved.geometry
            .buffer(SMOOTH_DIST, join_style="round")
            .buffer(-SMOOTH_DIST, join_style="round")
        )
        dissolved.geometry = dissolved.geometry.simplify(0.5, preserve_topology=True)
        dissolved = dissolved[~dissolved.geometry.is_empty]

        # Chaikinovo ořezávání rohů — z pořád hranatého (byť zaobleného) polygonu
        # udělá skutečně hladkou křivku bez jediného ostrého lomu.
        # POZOR: simplify() se NESMÍ volat po Chaikinu, znovu by vytvořil ostré rohy.
        CHAIKIN_ITERATIONS = 4
        dissolved["geometry"] = dissolved.geometry.apply(
            lambda g: _chaikin_smooth_geom(g, iterations=CHAIKIN_ITERATIONS)
        )
        dissolved = dissolved[~dissolved.geometry.is_empty]

        _cb(f"Vegetace vektorizována: {len(dissolved)} tříd")
        return dissolved
    except Exception as e:
        _cb(f"Chyba vektorizace vegetace: {e}")
        return gpd.GeoDataFrame(columns=["class_name", "class_id", "geometry"])


# ---------------------------------------------------------------------------
# Rock / cliff detection
# ---------------------------------------------------------------------------

def vectorize_rocks(grid_x: np.ndarray, grid_y: np.ndarray,
                    dmr_grid: np.ndarray, transform,
                    slope_threshold_deg: float = 54,
                    progress_cb=None) -> gpd.GeoDataFrame:
    """Detekuje skalní srázy podle sklonu terénu."""
    def _cb(msg):
        print(f"[processor] {msg}")
        if progress_cb:
            progress_cb(msg)

    _cb("Vektorizuji skály...")
    pixel_size_x = abs(transform.a)
    pixel_size_y = abs(transform.e)

    dy, dx = np.gradient(dmr_grid, pixel_size_y, pixel_size_x)
    slope = np.rad2deg(np.arctan(np.hypot(dx, dy)))

    valid_data_mask = (dmr_grid > 0) & (~np.isnan(dmr_grid))
    safe_mask = binary_erosion(valid_data_mask, iterations=7)
    rock_mask_raw = (slope > slope_threshold_deg) & safe_mask

    rock_area = rock_mask_raw.astype(np.int32).T
    rock_area = np.flipud(rock_area)

    pixel_area = pixel_size_x * pixel_size_y
    min_area = 10 * pixel_area

    if not np.any(rock_area):
        return gpd.GeoDataFrame(columns=["class_name", "geometry"])

    try:
        results = rasterio.features.shapes(rock_area, mask=(rock_area != 0), transform=transform)
        features = [{"geometry": shape(geom), "class_name": "Skala"} for geom, _ in results]
        if not features:
            return gpd.GeoDataFrame(columns=["class_name", "geometry"])
        gdf = gpd.GeoDataFrame(features)
        gdf = gdf[gdf.geometry.area >= min_area]
        gdf.geometry = gdf.geometry.buffer(0.4)
        dissolved = gdf.dissolve(by="class_name").reset_index()

        # Zaoblení hran — stejný princip jako u vegetace, ale s menším poloměrem:
        # skalní útvary bývají menší a detailnější, velký SMOOTH_DIST by je smazal.
        ROCK_SMOOTH_DIST = 1.0  # metry
        dissolved.geometry = (
            dissolved.geometry
            .buffer(ROCK_SMOOTH_DIST, join_style="round")
            .buffer(-ROCK_SMOOTH_DIST, join_style="round")
        )
        dissolved.geometry = dissolved.geometry.simplify(0.3, preserve_topology=True)
        dissolved = dissolved[~dissolved.geometry.is_empty]

        # Chaikinovo ořezávání rohů — hladká křivka bez ostrých lomů.
        # POZOR: simplify() se NESMÍ volat po Chaikinu, znovu by vytvořil ostré rohy.
        ROCK_CHAIKIN_ITERATIONS = 3
        dissolved["geometry"] = dissolved.geometry.apply(
            lambda g: _chaikin_smooth_geom(g, iterations=ROCK_CHAIKIN_ITERATIONS)
        )
        dissolved = dissolved[~dissolved.geometry.is_empty]

        _cb("Skály vektorizovány")
        return dissolved
    except Exception as e:
        _cb(f"Chyba vektorizace skal: {e}")
        return gpd.GeoDataFrame(columns=["class_name", "geometry"])


# ---------------------------------------------------------------------------
# Fill sinks (depressions + knolls)
# ---------------------------------------------------------------------------

def _fill_depressions_numpy(dem: np.ndarray, iterations: int = 50) -> np.ndarray:
    """Numpy implementace Fill Sinks bez externích závislostí."""
    from scipy.ndimage import minimum_filter
    filled = dem.copy()
    border_val = np.nanmin(dem) - 1.0
    filled[0, :] = border_val
    filled[-1, :] = border_val
    filled[:, 0] = border_val
    filled[:, -1] = border_val
    for _ in range(iterations):
        neighbor_min = minimum_filter(filled, size=3, mode="nearest")
        new_filled = np.maximum(dem, neighbor_min)
        new_filled[0, :] = border_val
        new_filled[-1, :] = border_val
        new_filled[:, 0] = border_val
        new_filled[:, -1] = border_val
        if np.allclose(new_filled, filled, atol=1e-6):
            break
        filled = new_filled
    return filled


def _compute_depth_grid(fill_input: np.ndarray, grid_x: np.ndarray,
                         grid_y: np.ndarray, current_crs: str,
                         invert: bool = False) -> np.ndarray:
    """Spočítá depth/height grid přes pysheds nebo numpy fallback."""
    data = (-fill_input) if invert else fill_input
    try:
        from pysheds.grid import Grid as PyshedsGrid
        min_x, max_x = grid_x.min(), grid_x.max()
        min_y, max_y = grid_y.min(), grid_y.max()
        tform = from_bounds(min_x, min_y, max_x, max_y, data.shape[0], data.shape[1])
        with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
            tmp_path = tmp.name
        dem_for_write = data.T
        with rasterio.open(
            tmp_path, "w", driver="GTiff",
            height=dem_for_write.shape[0], width=dem_for_write.shape[1],
            count=1, dtype=dem_for_write.dtype, crs=current_crs,
            transform=tform, nodata=-9999,
        ) as dst:
            dst.write(dem_for_write, 1)
        grid = PyshedsGrid.from_raster(tmp_path)
        dem_rd = grid.read_raster(tmp_path)
        pit_filled = grid.fill_pits(dem_rd)
        dem_filled = grid.fill_depressions(pit_filled)
        depth = (np.array(dem_filled) - np.array(dem_rd)).T
        os.unlink(tmp_path)
        return depth
    except Exception:
        filled = _fill_depressions_numpy(data.T.astype(np.float64))
        return (filled - data.T).T


def find_depressions(grid_x, grid_y, dmr_grid, pixel_size=0.5,
                     min_diameter=1, max_diameter=5, min_depth=0.5,
                     current_crs="EPSG:5514", progress_cb=None) -> list:
    """Vrátí seznam Point geometrií pro malé prohlubně."""
    def _cb(msg):
        if progress_cb:
            progress_cb(msg)

    _cb("Hledám prohlubně...")
    valid_mask = (dmr_grid > 0) & (~np.isnan(dmr_grid))
    safe_mask = binary_erosion(valid_mask, iterations=3)
    fill_mean = np.nanmean(dmr_grid[valid_mask])
    fill_input = np.where(np.isnan(dmr_grid) | ~valid_mask, fill_mean, dmr_grid)

    depth_grid = _compute_depth_grid(fill_input, grid_x, grid_y, current_crs, invert=False)
    depression_mask = (depth_grid > min_depth) & safe_mask

    labeled, _ = label(depression_mask)
    slices = find_objects(labeled)
    pts = []
    for slc in slices:
        region = labeled[slc]
        region_mask = region > 0
        ny, nx = region_mask.shape
        diameter = max(ny, nx) * pixel_size
        if not (min_diameter <= diameter <= max_diameter):
            continue
        cy, cx = np.argwhere(region_mask).mean(axis=0)
        i0 = int(slc[0].start + cy)
        j0 = int(slc[1].start + cx)
        if i0 < dmr_grid.shape[0] and j0 < dmr_grid.shape[1]:
            pts.append(Point(float(grid_x[i0, j0]), float(grid_y[i0, j0])))
    _cb(f"Nalezeno {len(pts)} prohlubní")
    return pts


def find_knolls(grid_x, grid_y, dmr_grid, pixel_size=0.5,
                min_diameter=1.5, max_diameter=10, min_height=0.5,
                current_crs="EPSG:5514", progress_cb=None) -> list:
    """Vrátí seznam Point geometrií pro kupky."""
    def _cb(msg):
        if progress_cb:
            progress_cb(msg)

    _cb("Hledám kupky...")
    valid_mask = (dmr_grid > 0) & (~np.isnan(dmr_grid))
    safe_mask = binary_erosion(valid_mask, iterations=3)
    fill_mean = np.nanmean(dmr_grid[valid_mask])
    fill_input = np.where(np.isnan(dmr_grid) | ~valid_mask, fill_mean, dmr_grid)

    height_grid = _compute_depth_grid(fill_input, grid_x, grid_y, current_crs, invert=True)
    knoll_mask = (height_grid > min_height) & safe_mask

    labeled, _ = label(knoll_mask)
    slices = find_objects(labeled)
    pts = []
    for slc in slices:
        region = labeled[slc]
        region_mask = region > 0
        ny, nx = region_mask.shape
        diameter = max(ny, nx) * pixel_size
        if not (min_diameter <= diameter <= max_diameter):
            continue
        cy, cx = np.argwhere(region_mask).mean(axis=0)
        i0 = int(slc[0].start + cy)
        j0 = int(slc[1].start + cx)
        if i0 < dmr_grid.shape[0] and j0 < dmr_grid.shape[1]:
            pts.append(Point(float(grid_x[i0, j0]), float(grid_y[i0, j0])))
    _cb(f"Nalezeno {len(pts)} kupek")
    return pts


# ---------------------------------------------------------------------------
# Clip polygon from DTM points
# ---------------------------------------------------------------------------

def make_clip_polygon(points: np.ndarray):
    """Vytvoří konvexní obal z DTM bodů pro ořez vrstev."""
    try:
        safe = points[np.isfinite(points).all(axis=1)]
        poly = MultiPoint(safe).convex_hull
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly
    except Exception as e:
        print(f"[processor] Clip polygon error: {e}")
        return None