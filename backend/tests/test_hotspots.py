import numpy as np
import pytest
from pipeline.hotspots import extract_hotspots


def test_extract_hotspots_synthetic_blobs():
    # Create 100x100 grid (stride = 224 µm => total grid size 22.4 mm x 22.4 mm)
    ny, nx = 100, 100
    prob_grid = np.zeros((ny, nx), dtype=np.float32)

    # Blob 1: Center around (30, 30), radius ~10 cells (~5 mm²)
    y, x = np.ogrid[:ny, :nx]
    dist1 = np.sqrt((y - 30)**2 + (x - 30)**2)
    prob_grid[dist1 <= 10] = 0.95

    # Blob 2: Center around (70, 70), radius ~6 cells (~1.8 mm²)
    dist2 = np.sqrt((y - 70)**2 + (x - 70)**2)
    prob_grid[dist2 <= 6] = 0.85

    # Set some cells to NaN (no tissue)
    prob_grid[0:10, 0:10] = np.nan

    cfg = {
        "sigma": 2.0,
        "prob_threshold": 0.5,
        "min_area_mm2": 0.5,
        "max_hotspots": 8,
        "margin_um": 100.0,
        "simplify_tolerance_um": 50.0
    }

    hotspots = extract_hotspots(
        prob_grid=prob_grid,
        grid_origin_um=(0.0, 0.0),
        stride_um=224.0,
        cfg=cfg
    )

    assert len(hotspots) == 2
    assert hotspots[0]["id"] == "hs_01"
    assert hotspots[1]["id"] == "hs_02"
    assert hotspots[0]["prob_mean"] >= 0.8
    assert hotspots[0]["area_mm2"] > 0.5
    assert len(hotspots[0]["polygon_um"]) > 3


def test_extract_hotspots_empty_and_nan():
    prob_grid = np.full((50, 50), np.nan, dtype=np.float32)
    cfg = {
        "sigma": 2.0,
        "prob_threshold": 0.5,
        "min_area_mm2": 0.5,
        "max_hotspots": 8,
        "margin_um": 100.0,
        "simplify_tolerance_um": 50.0
    }

    hotspots = extract_hotspots(
        prob_grid=prob_grid,
        grid_origin_um=(0.0, 0.0),
        stride_um=224.0,
        cfg=cfg
    )

    assert hotspots == []


def test_extract_hotspots_min_area_filter():
    ny, nx = 50, 50
    prob_grid = np.zeros((ny, nx), dtype=np.float32)

    # Very small blob: 2x2 cells (2 * 224 µm = 448 µm => ~0.2 mm² < 0.5 mm²)
    prob_grid[10:12, 10:12] = 0.9

    cfg = {
        "sigma": 1.0,
        "prob_threshold": 0.5,
        "min_area_mm2": 0.5,
        "max_hotspots": 8,
        "margin_um": 50.0,
        "simplify_tolerance_um": 10.0
    }

    hotspots = extract_hotspots(
        prob_grid=prob_grid,
        grid_origin_um=(0.0, 0.0),
        stride_um=224.0,
        cfg=cfg
    )

    assert len(hotspots) == 0
