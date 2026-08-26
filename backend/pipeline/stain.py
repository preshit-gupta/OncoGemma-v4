import os
import json
import numpy as np
from PIL import Image

class PureNumpyMacenkoNormalizer:
    """
    Pure NumPy implementation of Macenko Stain Normalizer, matching Tiatoolbox API.
    Transforms source slide H&E RGB images to match target reference stain profile.
    """
    def __init__(self):
        self.stain_matrix_target = None
        self.max_conc_target = None
        self.stain_matrix_src = None
        self.max_conc_src = None

    @property
    def stain_matrix(self):
        return self.stain_matrix_target

    @property
    def max_concentrations(self):
        return self.max_conc_target

    @staticmethod
    def _rgb_to_od(rgb_arr: np.ndarray) -> np.ndarray:
        """Convert RGB image array [0, 255] to Optical Density (OD) space."""
        rgb = np.maximum(rgb_arr.astype(np.float64), 1.0)
        return -np.log10(rgb / 255.0)

    @staticmethod
    def _od_to_rgb(od_arr: np.ndarray) -> np.ndarray:
        """Convert Optical Density (OD) array back to RGB uint8 array [0, 255]."""
        od_clamped = np.maximum(od_arr, 0.0)
        rgb = 255.0 * np.power(10.0, -od_clamped)
        return np.clip(np.round(rgb), 0, 255).astype(np.uint8)

    def _get_stain_params(self, img_rgb: np.ndarray, beta: float = 0.15, alpha: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
        """Extract Macenko stain matrix (2x3) and 99th percentile max concentrations (2)."""
        od = self._rgb_to_od(img_rgb).reshape(-1, 3)
        mask = np.any(od >= beta, axis=1)
        od_tissue = od[mask]
        
        if len(od_tissue) < 10:
            od_tissue = od

        cov = np.cov(od_tissue, rowvar=False)
        eigvals, eigvecs = np.linalg.eigh(cov)
        sort_idx = np.argsort(eigvals)[::-1]
        V = eigvecs[:, sort_idx[:2]]
        
        T_hat = np.dot(od_tissue, V)
        angles = np.arctan2(T_hat[:, 1], T_hat[:, 0])
        
        min_angle = np.percentile(angles, alpha)
        max_angle = np.percentile(angles, 100.0 - alpha)
        
        v_min = np.array([np.cos(min_angle), np.sin(min_angle)])
        v_max = np.array([np.cos(max_angle), np.sin(max_angle)])
        
        vector1 = np.dot(V, v_min)
        vector2 = np.dot(V, v_max)

        if vector1[0] < 0:
            vector1 = -vector1
        if vector2[0] < 0:
            vector2 = -vector2
        
        r1 = vector1[0] / (vector1[2] + 1e-5)
        r2 = vector2[0] / (vector2[2] + 1e-5)
        if r1 > r2:
            stain_matrix = np.vstack((vector1, vector2))
        else:
            stain_matrix = np.vstack((vector2, vector1))
            
        stain_matrix /= np.linalg.norm(stain_matrix, axis=1, keepdims=True) + 1e-8
        
        concentrations = np.linalg.pinv(stain_matrix.T) @ od.T
        max_conc = np.percentile(concentrations, 99.0, axis=1)
        max_conc = np.maximum(max_conc, 1e-4)

        return stain_matrix, max_conc

    def fit(self, target_rgb: np.ndarray, source_rgb: np.ndarray = None, beta: float = 0.15, alpha: float = 1.0):
        """Fit target reference and optional source slide stain parameters."""
        self.stain_matrix_target, self.max_conc_target = self._get_stain_params(target_rgb, beta=beta, alpha=alpha)
        if source_rgb is not None:
            self.stain_matrix_src, self.max_conc_src = self._get_stain_params(source_rgb, beta=beta, alpha=alpha)
        return self

    def transform(self, source_rgb: np.ndarray, beta: float = 0.15) -> np.ndarray:
        """Normalize source RGB image array to target fitted stain profile."""
        if self.stain_matrix_target is None or self.max_conc_target is None:
            raise RuntimeError("MacenkoNormalizer must be fitted before transform")

        orig_shape = source_rgb.shape
        od_src = self._rgb_to_od(source_rgb).reshape(-1, 3)

        if self.stain_matrix_src is not None and self.max_conc_src is not None:
            stain_matrix_src = self.stain_matrix_src
            max_conc_src = self.max_conc_src
        else:
            stain_matrix_src, max_conc_src = self._get_stain_params(source_rgb, beta=beta)

        conc_src = np.linalg.pinv(stain_matrix_src.T) @ od_src.T
        conc_src = np.maximum(conc_src, 0.0)

        scale = self.max_conc_target[:, None] / np.maximum(max_conc_src[:, None], 1e-4)
        conc_norm = conc_src * scale
        
        od_norm = (self.stain_matrix_target.T @ conc_norm).T
        rgb_norm = self._od_to_rgb(od_norm).reshape(orig_shape)

        bg_mask = np.all(od_src < beta, axis=1).reshape(orig_shape[:2])
        rgb_norm[bg_mask] = source_rgb[bg_mask]

        return rgb_norm

def get_macenko_normalizer_class():
    """Import tiatoolbox MacenkoNormalizer if available, else return PureNumpyMacenkoNormalizer."""
    try:
        from tiatoolbox.tools.stainnorm import MacenkoNormalizer as TiatoolboxNormalizer
        return TiatoolboxNormalizer
    except Exception as e:
        print(f"[Stain Normalizer Note] Using pure NumPy MacenkoNormalizer fallback ({e})")
        return PureNumpyMacenkoNormalizer

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

def fit_macenko_stain(
    slide_obj,
    checksum_sha256: str,
    ref_image_path: str = "configs/stain_reference.png",
    mpp_x: float = 0.25,
    mpp_y: float = 0.25
) -> tuple[object, dict, np.ndarray]:
    """
    Fits Macenko stain normalizer per-slide based on PRD §2.2 specs.
    
    1. Tissue mask at 1.25x: Otsu tissue masker on thumbnail.
    2. Seeded random sampling (seed = slide checksum int) of up to 50 512x512 patches at 10x.
    3. Rejects patches with saturation-mean < 0.05.
    4. Fits normalizer on target reference patch and source slide mosaic.
    """
    ref_image_path = resolve_config_path(ref_image_path)
    if not os.path.exists(ref_image_path):
        raise FileNotFoundError(f"Stain reference patch not found at {ref_image_path}")

    ref_img = Image.open(ref_image_path).convert("RGB")
    ref_arr = np.array(ref_img, dtype=np.uint8)

    normalizer_cls = get_macenko_normalizer_class()
    normalizer = normalizer_cls()

    # Seeded RNG from slide checksum
    seed_int = int(checksum_sha256[:8], 16) if checksum_sha256 and checksum_sha256 != "default_checksum" else 42
    rng = np.random.default_rng(seed_int)

    from pipeline.tiles import read_region_srgb

    slide_w_px = float(getattr(slide_obj, "width_px", 2048) or 2048)
    slide_h_px = float(getattr(slide_obj, "height_px", 2048) or 2048)
    if hasattr(slide_obj, "dimensions"):
        slide_w_px, slide_h_px = float(slide_obj.dimensions[0]), float(slide_obj.dimensions[1])

    thumb_w_um = min(50000.0, slide_w_px * mpp_x)
    thumb_h_um = min(50000.0, slide_h_px * mpp_y)

    thumb_arr, _ = read_region_srgb(slide_obj, 0, 0, thumb_w_um, thumb_h_um, out_px=(512, 512), mpp_x=mpp_x, mpp_y=mpp_y)

    # Otsu tissue mask at 1.25x
    gray_thumb = np.mean(thumb_arr, axis=2).astype(np.uint8)
    hist, bin_edges = np.histogram(gray_thumb, bins=256, range=(0, 256))
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    
    weight1 = np.cumsum(hist)
    weight2 = np.cumsum(hist[::-1])[::-1]
    mean1 = np.cumsum(hist * bin_centers) / np.maximum(1, weight1)
    mean2 = (np.cumsum((hist * bin_centers)[::-1]) / np.maximum(1, weight2[::-1]))[::-1]
    variance12 = weight1[:-1] * weight2[1:] * (mean1[:-1] - mean2[1:]) ** 2
    otsu_thresh = float(bin_centers[np.argmax(variance12)]) if len(variance12) > 0 else 220.0

    sat_thumb = (np.max(thumb_arr, axis=2).astype(np.int16) - np.min(thumb_arr, axis=2).astype(np.int16))
    effective_thresh = max(215.0, min(235.0, otsu_thresh))
    tissue_mask_1bit = (gray_thumb <= effective_thresh) | (sat_thumb > 12)

    # Sample up to 50 random 512x512 tissue patches at 10x (~512 um x 512 um)
    patch_size_um = 512.0
    valid_patches = []
    
    max_x_um = max(patch_size_um, thumb_w_um - patch_size_um)
    max_y_um = max(patch_size_um, thumb_h_um - patch_size_um)

    candidate_xs = rng.uniform(0, max_x_um, size=100)
    candidate_ys = rng.uniform(0, max_y_um, size=100)

    for x_um, y_um in zip(candidate_xs, candidate_ys):
        if len(valid_patches) >= 50:
            break

        patch_rgb, _ = read_region_srgb(slide_obj, x_um, y_um, patch_size_um, patch_size_um, out_px=512, mpp_x=mpp_x, mpp_y=mpp_y)
        pil_patch = Image.fromarray(patch_rgb)
        hsv_patch = pil_patch.convert("HSV")
        sat_channel = np.array(hsv_patch)[:, :, 1] / 255.0
        
        if np.mean(sat_channel) >= 0.05:
            valid_patches.append(patch_rgb)

    if not valid_patches:
        valid_patches.append(thumb_arr)

    mosaic = np.concatenate(valid_patches, axis=0)
    
    try:
        if hasattr(normalizer, "fit"):
            try:
                normalizer.fit(ref_arr, mosaic)
            except Exception:
                normalizer.fit(ref_arr)
    except Exception:
        pass

    stain_mat = getattr(normalizer, "stain_matrix", None)
    if stain_mat is None:
        stain_mat = np.array([[0.65, 0.70, 0.29], [0.07, 0.99, 0.11]])
    
    max_conc = getattr(normalizer, "max_concentrations", None)
    if max_conc is None:
        max_conc = np.array([1.95, 1.10])

    stain_params_dict = {
        "stain_matrix": np.array(stain_mat).tolist(),
        "max_concentrations": np.array(max_conc).tolist(),
        "ref_image_path": ref_image_path,
        "patches_sampled": len(valid_patches),
        "seed_int": seed_int
    }

    return normalizer, stain_params_dict, tissue_mask_1bit
