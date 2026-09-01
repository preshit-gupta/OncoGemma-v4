"""
OncoGemma Stage v4.3 - HoVer-Net Mitosis Verifier & Nuclear Morphometry Engine.
Performs second-pass instance segmentation and classification on 128x128 candidate crops.
Filters out apoptotic bodies, lymphocytes, and pyknotic debris from true mitotic figures.
"""
import os
import math
from typing import Protocol, Tuple, List, Optional
import numpy as np


class MitosisVerifier(Protocol):
    def verify(self, crop_rgb: np.ndarray) -> Tuple[float, Optional[List[List[int]]]]:
        """
        Evaluates a 128x128 crop centered at candidate centroid.
        Returns:
            p_mitosis: Probability (0.0 to 1.0) that crop contains a genuine mitotic figure.
            contour: Approximate boundary coordinates [[x1, y1], [x2, y2], ...] of the central nucleus.
        """
        ...


class HoVerNetMitosisVerifier:
    """
    HoVer-Net Architecture & Morphological Nuclear Instance Verifier.
    Differentiates true mitotic figures (metaphase plates, anaphase spindles, telophase clusters)
    from resting tumor nuclei, lymphocytes, apoptotic fragments, and debris.
    """
    def __init__(self, weights_path: Optional[str] = None, threshold: float = 0.50, device: str = "cpu"):
        self.weights_path = weights_path
        self.threshold = threshold
        self.device = device
        self.model = None
        self.model_version = "hovernet_fast_mitosis@v1.2"

        if weights_path and os.path.exists(weights_path):
            try:
                import torch
                self.model = torch.load(weights_path, map_location=device)
                print(f"[HoVerNetVerifier] Loaded weights from {weights_path}")
            except Exception as e:
                print(f"[HoVerNetVerifier Warning] Failed to load {weights_path}: {e}. Using morphological verification engine.")
                self.model = None

    def verify(self, crop_rgb: np.ndarray) -> Tuple[float, Optional[List[List[int]]]]:
        """
        Evaluates a 128x128 crop at 0.25 um/px.
        """
        h, w, _ = crop_rgb.shape
        if h < 32 or w < 32:
            return 0.0, None

        if self.model is not None:
            try:
                import torch
                img_t = torch.from_numpy(crop_rgb).permute(2, 0, 1).float() / 255.0
                img_t = img_t.unsqueeze(0).to(self.device)
                with torch.no_grad():
                    output = self.model(img_t)
                # Output has tp_map (nuclear type prediction) and np_map (nuclear pixel map)
                p_mitosis = float(output.get("p_mitosis", 0.5))
                return p_mitosis, None
            except Exception as e:
                print(f"[HoVerNet Runtime Error] {e}. Falling back to morphometric classifier.")

        # Morphometric nuclear instance analysis on 128x128 patch
        return self._morphometric_nuclear_analysis(crop_rgb)

    def _morphometric_nuclear_analysis(self, crop_rgb: np.ndarray) -> Tuple[float, Optional[List[List[int]]]]:
        """
        First-principles cellular morphometry:
        1. Analyzes central region for chromatin condensation and nuclear morphology.
        2. Measures boundary irregularity / spiculation (spindle protrusions vs smooth lymphocyte/nuclear envelope).
        3. Detects absence of intact nuclear membrane (classic hallmark of active mitosis).
        4. Explicitly filters out non-mitotic mimickers:
           - Apoptotic bodies (small, dense, pyknotic, high circularity, haloed)
           - Lymphocytes (small, smooth continuous unbroken envelope, high circularity/solidity)
           - Resting / interphase nuclei (intact membrane, vesicular chromatin, lower OD)
           - Background stroma / debris / dust specks
        """
        try:
            import cv2
        except ImportError:
            cv2 = None

        h, w, _ = crop_rgb.shape
        cy, cx = h // 2, w // 2
        r_px = min(24, min(h, w) // 4) # ~12 um radius region

        # Optical density transformation
        rgb_f = np.maximum(crop_rgb.astype(np.float32), 1.0) / 255.0
        od = -np.log(rgb_f)
        # Hematoxylin absorption component
        h_od = od[:, :, 0] - 0.15 * od[:, :, 1] - 0.15 * od[:, :, 2]

        center_h_od = h_od[cy - r_px : cy + r_px, cx - r_px : cx + r_px]
        mean_h_od = float(np.mean(center_h_od))

        # Reject empty background / stroma
        if mean_h_od < 0.20:
            return 0.05, None

        # Robust 95th percentile OD (avoids single-pixel outlier blowout)
        p95_od = float(np.percentile(center_h_od, 95))
        std_od = float(np.std(center_h_od))

        # Segment central chromatin clump
        thresh = max(0.35, float(np.median(h_od) + 1.2 * np.std(h_od)))
        chromatin_mask = (center_h_od > thresh).astype(np.uint8) * 255

        contour_pts = None

        if cv2 is not None:
            cnts, _ = cv2.findContours(chromatin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            if not cnts:
                return 0.10, None

            # Filter to contours close to center
            # Extract the central connected component located at (r_px, r_px)
            central_cnt = None
            for cnt in cnts:
                if cv2.pointPolygonTest(cnt, (r_px, r_px), False) >= -2.0:
                    central_cnt = cnt
                    break

            if central_cnt is None:
                # Fallback to closest contour within central radius
                central_cnt = min(cnts, key=lambda c: cv2.pointPolygonTest(c, (r_px, r_px), True) ** 2)

            area = float(cv2.contourArea(central_cnt))
            perim = float(cv2.arcLength(central_cnt, True))

            if area < 80 or perim <= 0:
                # Tiny debris / noise
                return 0.12, None

            equiv_diam = float(np.sqrt(4.0 * area / np.pi)) # diameter in pixels
            circ = float((4.0 * np.pi * area) / (perim * perim))
            hull = cv2.convexHull(central_cnt)
            hull_area = max(1.0, float(cv2.contourArea(hull)))
            solidity = float(area / hull_area)

            equiv_perim = np.pi * equiv_diam
            spiculation = float((perim - equiv_perim) / max(1.0, equiv_perim))

            # Approximate nuclear contour in crop coordinates
            approx_cnt = cv2.approxPolyDP(central_cnt, 1.5, True)
            contour_pts = []
            for pt in approx_cnt:
                px_crop = int(pt[0][0] + (cx - r_px))
                py_crop = int(pt[0][1] + (cy - r_px))
                contour_pts.append([px_crop, py_crop])

            # 1. Reject Apoptotic Fragments / Small Pyknotic Debris:
            # Mitotic figures in breast carcinoma are 10-18 um (40-72 px diameter).
            # Anything with diam < 20 px (< 5 um) or area < 300 px2 is an apoptotic body, pyknotic fragment, or debris.
            if equiv_diam < 20.0 or area < 300.0:
                return 0.15, contour_pts

            # 2. Reject Lymphocyte / Inflammatory Cell:
            # Smooth continuous circular membrane (circ > 0.65, solidity > 0.88, spiculation < 0.20, low texture std < 0.28)
            if 20 <= equiv_diam <= 32 and circ > 0.65 and solidity > 0.88 and spiculation < 0.20 and std_od < 0.28:
                return 0.20, contour_pts

            # 3. Reject Normal / Resting Tumor Nucleus (Solitary or Crowded Sheet):
            # Smooth membrane, lower chromatin condensation (p95_od < 0.95 and std_od < 0.30, spiculation < 0.22, solidity > 0.85)
            if spiculation < 0.22 and solidity > 0.85 and p95_od < 0.95 and std_od < 0.30:
                return 0.28, contour_pts

            # 4. Reject Massive Tissue Fold / Stain Clump:
            if area > 3500 or equiv_diam > 65.0:
                return 0.20, contour_pts

            # 5. Mitotic Figure Scoring (True dividing cell with dissolved envelope and hairy spicules):
            # - Size score: centered around 24-55 px (6-14 um)
            size_score = float(np.clip((equiv_diam - 20.0) / 22.0, 0.0, 1.0))
            # - Spiculation / lack of intact membrane (spiculation >= 0.15)
            spic_score = float(np.clip((spiculation - 0.15) / 0.45, 0.0, 1.0))
            # - Chromatin condensation (p95_od >= 0.75)
            od_score = float(np.clip((p95_od - 0.75) / 0.75, 0.0, 1.0))
            # - Texture variance from chromosome clumps (std_od >= 0.20)
            texture_score = float(np.clip((std_od - 0.20) / 0.35, 0.0, 1.0))
            # - Irregularity (lower solidity from jagged boundary)
            irregularity_score = float(np.clip((1.0 - solidity) / 0.30, 0.0, 1.0))

            p_mitosis = 0.15 + (
                0.25 * spic_score +
                0.25 * od_score +
                0.25 * texture_score +
                0.15 * size_score +
                0.10 * irregularity_score
            )

            return float(np.clip(p_mitosis, 0.05, 0.95)), contour_pts
        else:
            # Fallback when OpenCV is not installed
            dense_pixels = int(np.sum(chromatin_mask > 0))
            if dense_pixels < 30:
                return 0.12, None
            score = 0.20 + min(0.70, (dense_pixels / 600.0) * 0.35 + (p95_od / 2.0) * 0.35)
            return float(np.clip(score, 0.05, 0.95)), None
