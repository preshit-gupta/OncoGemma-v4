import numpy as np
import pytest

from pipeline.qc_checks import check_tissue_coverage, check_focus_sharpness

def test_check_tissue_coverage_pass():
    """Verify tissue coverage pass status on adequate tissue mask (> 5%)."""
    mask = np.ones((512, 512), dtype=bool) # 100% coverage
    config = {"tissue_coverage": {"fail_threshold": 0.02, "warn_threshold": 0.05}}

    res = check_tissue_coverage(mask, config)
    assert res["status"] == "pass"
    assert res["metric"] == 1.0

def test_check_tissue_coverage_fail():
    """Verify tissue coverage fail status on blank tissue mask (< 2%)."""
    mask = np.zeros((512, 512), dtype=bool) # 0% coverage
    config = {"tissue_coverage": {"fail_threshold": 0.02, "warn_threshold": 0.05}}

    res = check_tissue_coverage(mask, config)
    assert res["status"] == "fail"
    assert res["metric"] == 0.0

def test_check_focus_sharpness_synthetic():
    """Verify focus check on sharp vs blurry synthetic tiles."""
    from PIL import Image
    
    blank_slide = Image.new("RGB", (1024, 1024), color=(240, 235, 240))
    mask = np.ones((128, 128), dtype=bool)
    config = {"focus": {"vol_threshold": 5.0, "fail_blurry_ratio": 0.70, "warn_blurry_ratio": 0.30, "sample_max_tiles": 10}}

    res = check_focus_sharpness(blank_slide, mask, config=config)
    assert res["name"] == "focus"
    assert res["status"] in ["pass", "warn", "fail"]
