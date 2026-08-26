import os
import yaml
import hashlib
import cv2
import numpy as np

def resolve_config_path(path: str) -> str:
    """Resolve config file path relative to repo root or backend parent directory."""
    if os.path.isabs(path) and os.path.exists(path):
        return path
    if os.path.exists(path):
        return os.path.abspath(path)

    parent_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../", path))
    if os.path.exists(parent_path):
        return parent_path

    return os.path.abspath(path)

def load_qc_config(config_path: str = "configs/qc.yaml") -> tuple[dict, str]:
    """Load QC thresholds configuration YAML and calculate MD5 config hash."""
    config_path = resolve_config_path(config_path)
    if not os.path.exists(config_path):
        # Fallback default configuration dictionary
        default_cfg = {
            "tissue_coverage": {"fail_threshold": 0.02, "warn_threshold": 0.05},
            "focus": {"vol_threshold": 5.0, "fail_blurry_ratio": 0.70, "warn_blurry_ratio": 0.30, "sample_max_tiles": 400}
        }
        return default_cfg, "default_hash"

    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    config_dict = yaml.safe_load(content) or {}
    config_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
    return config_dict, config_hash

def check_tissue_coverage(tissue_mask_1bit: np.ndarray, config: dict) -> dict:
    """
    Check 1: Tissue Coverage
    tissue mask area / total thumbnail area.
    < 2% -> fail; < 5% -> warn.
    """
    cfg = config.get("tissue_coverage", {})
    fail_thresh = cfg.get("fail_threshold", 0.02)
    warn_thresh = cfg.get("warn_threshold", 0.05)

    total_pixels = tissue_mask_1bit.size
    tissue_pixels = np.count_nonzero(tissue_mask_1bit)
    coverage_ratio = float(tissue_pixels / max(1, total_pixels))

    status = "pass"
    if coverage_ratio < fail_thresh:
        status = "fail"
        msg = f"Critical low tissue coverage: {coverage_ratio * 100:.1f}% (threshold < {fail_thresh * 100:.0f}%)"
    elif coverage_ratio < warn_thresh:
        status = "warn"
        msg = f"Low tissue coverage: {coverage_ratio * 100:.1f}% (threshold < {warn_thresh * 100:.0f}%)"
    else:
        msg = f"Adequate tissue coverage: {coverage_ratio * 100:.1f}%"

    return {
        "name": "tissue_coverage",
        "status": status,
        "metric": round(coverage_ratio, 4),
        "message": msg
    }

def check_focus_sharpness(
    slide_obj,
    tissue_mask_1bit: np.ndarray,
    mpp_x: float = 0.25,
    mpp_y: float = 0.25,
    config: dict = None
) -> dict:
    """
    Check 2: Focus Sharpness
    Variance of Laplacian (OpenCV, grayscale) per 512^2 tile at 10x, on <= 400 sampled tissue tiles.
    """
    cfg = (config or {}).get("focus", {})
    vol_thresh = cfg.get("vol_threshold", 5.0)
    fail_blurry_ratio = cfg.get("fail_blurry_ratio", 0.70)
    warn_blurry_ratio = cfg.get("warn_blurry_ratio", 0.30)
    max_tiles = cfg.get("sample_max_tiles", 400)

    from pipeline.tiles import read_region_srgb

    patch_size_um = 512.0
    thumb_h, thumb_w = tissue_mask_1bit.shape
    slide_w_um = thumb_w * 8.0 * mpp_x
    slide_h_um = thumb_h * 8.0 * mpp_y

    blurry_tile_count = 0
    total_sampled_tiles = 0

    step_um = patch_size_um * 2
    xs = np.arange(0, max(patch_size_um, slide_w_um - patch_size_um), step_um)
    ys = np.arange(0, max(patch_size_um, slide_h_um - patch_size_um), step_um)

    positions = [(x, y) for x in xs for y in ys]

    if len(positions) > max_tiles:
        rng = np.random.default_rng(42)
        idx_sample = rng.choice(len(positions), size=max_tiles, replace=False)
        positions = [positions[i] for i in idx_sample]

    for x_um, y_um in positions:
        try:
            tile_rgb, _ = read_region_srgb(slide_obj, x_um, y_um, patch_size_um, patch_size_um, out_px=512, mpp_x=mpp_x, mpp_y=mpp_y)
            if np.std(tile_rgb) > 5.0:
                gray = cv2.cvtColor(tile_rgb, cv2.COLOR_RGB2GRAY)
                vol = cv2.Laplacian(gray, cv2.CV_64F).var()
                
                total_sampled_tiles += 1
                if vol < vol_thresh:
                    blurry_tile_count += 1
        except Exception:
            pass

    blurry_ratio = float(blurry_tile_count / max(1, total_sampled_tiles)) if total_sampled_tiles > 0 else 0.0

    status = "pass"
    if total_sampled_tiles > 0 and blurry_ratio > fail_blurry_ratio:
        status = "fail"
        msg = f"Critical focus blur: {blurry_ratio * 100:.1f}% of tissue tiles blurry (threshold > {fail_blurry_ratio * 100:.0f}%)"
    elif total_sampled_tiles > 0 and blurry_ratio > warn_blurry_ratio:
        status = "warn"
        msg = f"{blurry_ratio * 100:.1f}% of tissue tiles below sharpness threshold (VoL < {vol_thresh})"
    else:
        msg = f"Slide focus sharp ({blurry_ratio * 100:.1f}% blurry tiles)"

    return {
        "name": "focus",
        "status": status,
        "metric": round(blurry_ratio, 4),
        "message": msg
    }

def run_all_qc_checks(
    slide_obj,
    tissue_mask_1bit: np.ndarray,
    mpp_x: float = 0.25,
    mpp_y: float = 0.25,
    config_path: str = "configs/qc.yaml"
) -> dict:
    """Execute simplified QC check suite (tissue coverage & focus sharpness)."""
    config_dict, config_hash = load_qc_config(config_path)

    # 1. Tissue coverage
    cov_res = check_tissue_coverage(tissue_mask_1bit, config_dict)

    # 2. Focus sharpness
    focus_res = check_focus_sharpness(slide_obj, tissue_mask_1bit, mpp_x=mpp_x, mpp_y=mpp_y, config=config_dict)

    checks = [cov_res, focus_res]

    statuses = [c["status"] for c in checks]
    if "fail" in statuses:
        overall_verdict = "fail"
    elif "warn" in statuses:
        overall_verdict = "warn"
    else:
        overall_verdict = "pass"

    return {
        "verdict": overall_verdict,
        "checks": checks,
        "config_hash": config_hash
    }
