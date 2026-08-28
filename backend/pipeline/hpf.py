"""
OncoGemma Stage v4.3 - Pure HPF Placement & Spatial Density Engine.
Convolves confirmed mitotic coordinates with a circular HPF kernel (radius = 262 um)
using FFT, and performs greedy non-overlapping placement of 10 virtual High-Power Fields.
"""
import math
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from scipy.signal import fftconvolve


def create_circular_disk_mask(radius_cells: float) -> np.ndarray:
    """
    Creates a discrete circular disk mask kernel of given radius in cells.
    """
    r_ceil = int(math.ceil(radius_cells))
    size = 2 * r_ceil + 1
    y, x = np.ogrid[-r_ceil:r_ceil + 1, -r_ceil:r_ceil + 1]
    mask = (x * x + y * y) <= (radius_cells * radius_cells)
    return mask.astype(np.float32)


def generate_mitosis_density_map(
    candidates: List[Dict[str, Any]],
    bounding_box_um: Tuple[float, float, float, float],
    grid_res_um: float = 16.0,
    radius_um: float = 262.0
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Splats candidate mitotic figures onto a 16 um spatial grid and convolves
    with a circular disk kernel equivalent to a 262 um HPF radius.

    Returns:
        density_map: 2D float32 array of continuous mitotic counts per HPF area.
        grid_meta: metadata dictionary containing origin_um, stride_um, nx, ny.
    """
    min_x_um, min_y_um, max_x_um, max_y_um = bounding_box_um

    # Add margin around bounding box equal to HPF radius
    pad_um = radius_um * 1.5
    min_x_um -= pad_um
    min_y_um -= pad_um
    max_x_um += pad_um
    max_y_um += pad_um

    nx = max(16, int(math.ceil((max_x_um - min_x_um) / grid_res_um)))
    ny = max(16, int(math.ceil((max_y_um - min_y_um) / grid_res_um)))

    point_grid = np.zeros((ny, nx), dtype=np.float32)

    # Splat candidates
    for cand in candidates:
        # Only splat confirmed or high-confidence candidate figures
        label = cand.get("label", "unreviewed")
        if label == "not_mitosis":
            continue

        cx_um, cy_um = cand["centroid_um"]
        gx = int(round((cx_um - min_x_um) / grid_res_um))
        gy = int(round((cy_um - min_y_um) / grid_res_um))

        if 0 <= gx < nx and 0 <= gy < ny:
            weight = 1.0
            if label == "unreviewed":
                weight = cand.get("ver_conf", cand.get("det_conf", 0.5))
            point_grid[gy, gx] += float(weight)

    # Convolve with circular disk kernel
    radius_cells = radius_um / grid_res_um
    kernel = create_circular_disk_mask(radius_cells)
    density_map = fftconvolve(point_grid, kernel, mode="same")
    density_map = np.maximum(density_map, 0.0)

    grid_meta = {
        "origin_um": [float(min_x_um), float(min_y_um)],
        "stride_um": float(grid_res_um),
        "nx": nx,
        "ny": ny,
        "radius_um": float(radius_um)
    }

    return density_map.astype(np.float32), grid_meta


def is_point_in_polygon(x: float, y: float, polygon: List[List[float]]) -> bool:
    """Ray-casting algorithm for point-in-polygon test."""
    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def greedy_place_hpfs(
    density_map: np.ndarray,
    grid_meta: Dict[str, Any],
    hotspot_polygons_um: Optional[List[List[List[float]]]] = None,
    count: int = 10,
    radius_um: float = 262.0,
    min_separation_um: float = 524.0,
    relaxed_min_separation_um: float = 393.0
) -> List[Dict[str, Any]]:
    """
    Greedily selects the top 10 virtual HPF coordinates from the mitotic density map.
    Enforces non-overlapping constraint (distance >= 2r). If fewer than 10 fit,
    relaxes minimum separation (distance >= 1.5r) to guarantee 10 fields are evaluated.
    """
    origin_x, origin_y = grid_meta["origin_um"]
    stride = grid_meta["stride_um"]
    ny, nx = density_map.shape

    working_density = density_map.copy()

    # Precompute mask for hotspot polygon constraints if provided
    tumor_mask = np.ones((ny, nx), dtype=bool)
    if hotspot_polygons_um:
        tumor_mask = np.zeros((ny, nx), dtype=bool)
        for gy in range(ny):
            py_um = origin_y + gy * stride
            for gx in range(nx):
                px_um = origin_x + gx * stride
                for poly in hotspot_polygons_um:
                    if poly and len(poly) >= 3 and is_point_in_polygon(px_um, py_um, poly):
                        tumor_mask[gy, gx] = True
                        break

    placed_hpfs: List[Dict[str, Any]] = []
    placed_centers: List[Tuple[float, float]] = []

    suppress_radius_cells = min_separation_um / stride

    # Pass 1: Strict non-overlapping placement (separation >= 2r)
    while len(placed_hpfs) < count:
        masked_density = working_density * tumor_mask
        max_val = np.max(masked_density)
        if max_val <= 0.0:
            break

        gy, gx = np.unravel_index(np.argmax(masked_density), masked_density.shape)
        cx_um = float(origin_x + gx * stride)
        cy_um = float(origin_y + gy * stride)

        # Verify separation
        valid = True
        for px, py in placed_centers:
            if math.hypot(cx_um - px, cy_um - py) < min_separation_um - 1e-3:
                valid = False
                break

        if valid:
            placed_centers.append((cx_um, cy_um))
            placed_hpfs.append({
                "seq": len(placed_hpfs) + 1,
                "center_um": [cx_um, cy_um],
                "radius_um": float(radius_um),
                "count": 0,
                "density_val": float(max_val),
                "source": "model"
            })

        # Suppress density within separation radius
        y_min = max(0, int(gy - suppress_radius_cells))
        y_max = min(ny, int(gy + suppress_radius_cells + 1))
        x_min = max(0, int(gx - suppress_radius_cells))
        x_max = min(nx, int(gx + suppress_radius_cells + 1))

        y_coords, x_coords = np.ogrid[y_min:y_max, x_min:x_max]
        dist_sq = (x_coords - gx) ** 2 + (y_coords - gy) ** 2
        circle_mask = dist_sq <= (suppress_radius_cells ** 2)
        working_density[y_min:y_max, x_min:x_max][circle_mask] = 0.0

    # Pass 2: Fallback with relaxed separation (>= 1.5r) if fewer than `count` fit and relaxed < min_sep
    if len(placed_hpfs) < count and relaxed_min_separation_um < min_separation_um:
        working_density = density_map.copy()
        r_relax_cells = relaxed_min_separation_um / stride
        for px, py in placed_centers:
            gx = (px - origin_x) / stride
            gy = (py - origin_y) / stride
            y_min = max(0, int(gy - r_relax_cells))
            y_max = min(ny, int(gy + r_relax_cells + 1))
            x_min = max(0, int(gx - r_relax_cells))
            x_max = min(nx, int(gx + r_relax_cells + 1))
            y_coords, x_coords = np.ogrid[y_min:y_max, x_min:x_max]
            dist_sq = (x_coords - gx) ** 2 + (y_coords - gy) ** 2
            circle_mask = dist_sq <= (r_relax_cells ** 2)
            working_density[y_min:y_max, x_min:x_max][circle_mask] = 0.0

        while len(placed_hpfs) < count:
            masked_density = working_density * tumor_mask
            max_val = np.max(masked_density)
            if max_val <= 0.0:
                break

            gy, gx = np.unravel_index(np.argmax(masked_density), masked_density.shape)
            cx_um = float(origin_x + gx * stride)
            cy_um = float(origin_y + gy * stride)

            valid = True
            for px, py in placed_centers:
                if math.hypot(cx_um - px, cy_um - py) < relaxed_min_separation_um - 1e-3:
                    valid = False
                    break

            if valid:
                placed_centers.append((cx_um, cy_um))
                placed_hpfs.append({
                    "seq": len(placed_hpfs) + 1,
                    "center_um": [cx_um, cy_um],
                    "radius_um": float(radius_um),
                    "count": 0,
                    "density_val": float(max_val),
                    "source": "model"
                })

            y_min = max(0, int(gy - r_relax_cells))
            y_max = min(ny, int(gy + r_relax_cells + 1))
            x_min = max(0, int(gx - r_relax_cells))
            x_max = min(nx, int(gx + r_relax_cells + 1))
            y_coords, x_coords = np.ogrid[y_min:y_max, x_min:x_max]
            circle_mask = ((x_coords - gx) ** 2 + (y_coords - gy) ** 2) <= (r_relax_cells ** 2)
            working_density[y_min:y_max, x_min:x_max][circle_mask] = 0.0

    # Pass 3: Geometry distribution fallback if tiny area
    while len(placed_hpfs) < count:
        seq_num = len(placed_hpfs) + 1
        if placed_centers:
            base_x, base_y = placed_centers[0]
        else:
            base_x = origin_x + (nx * stride) / 2.0
            base_y = origin_y + (ny * stride) / 2.0
        angle = seq_num * (2 * math.pi / count)
        dist_offset = (radius_um * 0.75) * (1 + (seq_num // 4))
        cx_um = base_x + dist_offset * math.cos(angle)
        cy_um = base_y + dist_offset * math.sin(angle)
        placed_hpfs.append({
            "seq": seq_num,
            "center_um": [float(cx_um), float(cy_um)],
            "radius_um": float(radius_um),
            "count": 0,
            "density_val": 0.0,
            "source": "model"
        })

    return placed_hpfs[:count]
