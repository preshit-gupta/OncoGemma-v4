"""
Pure functional logic for extracting hotspot ROIs from probability grids.
Independent of I/O, DB, or GCS. Fully unit-testable.
"""
from typing import Any
import numpy as np
from scipy.ndimage import gaussian_filter, label
from skimage.measure import find_contours
from shapely.geometry import Polygon


def extract_hotspots(
    prob_grid: np.ndarray,
    grid_origin_um: tuple[float, float],
    stride_um: float,
    cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    Extracts top hotspot ROIs from a 2D probability grid.

    Args:
        prob_grid: 2D float32 array [ny, nx] where NaN = no tissue.
        grid_origin_um: (origin_x_um, origin_y_um) in base slide coordinates.
        stride_um: Stride between grid cells in micrometers (e.g. 224 µm).
        cfg: Config dict containing sigma, prob_threshold, min_area_mm2, max_hotspots, margin_um, simplify_tolerance_um.

    Returns:
        List of Hotspot dictionaries containing polygon_um, area_mm2, prob_mean, prob_max, source, excluded.
    """
    sigma = float(cfg.get("sigma", 2.0))
    prob_threshold = float(cfg.get("prob_threshold", 0.5))
    min_area_mm2 = float(cfg.get("min_area_mm2", 0.5))
    max_hotspots = int(cfg.get("max_hotspots", 8))
    margin_um = float(cfg.get("margin_um", 100.0))
    simplify_tolerance_um = float(cfg.get("simplify_tolerance_um", 50.0))

    if prob_grid is None or prob_grid.size == 0:
        return []

    # 1. Handle NaNs during Gaussian smoothing via weight masking
    valid_mask = ~np.isnan(prob_grid)
    if not np.any(valid_mask):
        return []

    prob_filled = np.nan_to_num(prob_grid, nan=0.0)
    
    smoothed_prob = gaussian_filter(prob_filled, sigma=sigma)
    smoothed_weight = gaussian_filter(valid_mask.astype(float), sigma=sigma)
    
    # Avoid zero division
    with np.errstate(divide='ignore', invalid='ignore'):
        smoothed = np.where(smoothed_weight > 1e-5, smoothed_prob / smoothed_weight, 0.0)
    
    # Mask out non-tissue areas
    smoothed[~valid_mask] = 0.0

    # 2. Binary thresholding
    binary = smoothed >= prob_threshold
    if not np.any(binary):
        return []

    # 3. Connected components labeling
    labeled_grid, num_features = label(binary)
    if num_features == 0:
        return []

    cell_area_mm2 = (stride_um * stride_um) / 1e6
    components = []

    for comp_idx in range(1, num_features + 1):
        comp_mask = (labeled_grid == comp_idx)
        cell_count = np.sum(comp_mask)
        area_mm2 = cell_count * cell_area_mm2

        if area_mm2 < min_area_mm2:
            continue

        raw_probs = prob_filled[comp_mask]
        prob_sum = float(np.sum(raw_probs))
        prob_mean = float(np.mean(raw_probs))
        prob_max = float(np.max(raw_probs))

        components.append({
            "comp_idx": comp_idx,
            "comp_mask": comp_mask,
            "area_mm2": area_mm2,
            "prob_sum": prob_sum,
            "prob_mean": prob_mean,
            "prob_max": prob_max
        })

    if not components:
        return []

    # 4. Score & rank components by prob_sum; retain top N
    components.sort(key=lambda c: c["prob_sum"], reverse=True)
    top_components = components[:max_hotspots]

    hotspots = []
    origin_x, origin_y = grid_origin_um

    for i, comp in enumerate(top_components, start=1):
        mask_pad = np.pad(comp["comp_mask"], pad_width=1, mode='constant', constant_values=False)
        contours = find_contours(mask_pad.astype(float), 0.5)

        if not contours:
            continue

        # Use largest contour if multiple returned
        contours.sort(key=lambda c: len(c), reverse=True)
        main_contour = contours[0]

        # Convert contour coordinates (r, c) to base micrometers
        # Note: pad_width=1 shifts row/col by -1
        coords_um = []
        for r, c in main_contour:
            grid_c = c - 1.0
            grid_r = r - 1.0
            x_um = origin_x + (grid_c * stride_um)
            y_um = origin_y + (grid_r * stride_um)
            coords_um.append((x_um, y_um))

        if len(coords_um) < 3:
            continue

        poly = Polygon(coords_um)
        if not poly.is_valid:
            poly = poly.buffer(0)

        # Simplify & dilate by margin_um
        if simplify_tolerance_um > 0:
            poly = poly.simplify(simplify_tolerance_um, preserve_topology=True)
        if margin_um > 0:
            poly = poly.buffer(margin_um)

        if poly.is_empty or not hasattr(poly, 'exterior') or poly.exterior is None:
            continue

        final_coords = [[round(x, 2), round(y, 2)] for x, y in poly.exterior.coords]
        actual_area_mm2 = round(poly.area / 1e6, 3)

        hotspots.append({
            "id": f"hs_{i:02d}",
            "polygon_um": final_coords,
            "area_mm2": actual_area_mm2,
            "prob_mean": round(comp["prob_mean"], 3),
            "prob_max": round(comp["prob_max"], 3),
            "source": "model",
            "excluded": False,
            "exclude_reason": None
        })

    return hotspots
